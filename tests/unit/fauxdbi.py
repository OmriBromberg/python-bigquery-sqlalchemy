# Copyright (c) 2021 The PyBigQuery Authors
#
# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so,
# subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import base64
import contextlib
import datetime
import decimal
import pickle
import re
import sqlite3

import google.api_core.exceptions
import google.cloud.bigquery.schema
import google.cloud.bigquery.table
import google.cloud.bigquery.dbapi.cursor


class Connection:
    def __init__(self, connection, test_data, client, *args, **kw):
        self.connection = connection
        self.test_data = test_data
        self._client = client
        client.connection = self

    def cursor(self):
        return Cursor(self)

    def commit(self):
        pass


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.cursor = connection.connection.cursor()
        assert self.arraysize == 1

    __arraysize = 1

    @property
    def arraysize(self):
        return self.__arraysize

    @arraysize.setter
    def arraysize(self, v):
        self.__arraysize = v
        self.connection.test_data["arraysize"] = v

    _need_to_be_pickled = (
        list,
        dict,
        decimal.Decimal,
        bool,
        datetime.datetime,
        datetime.date,
        datetime.time,
    )

    def __convert_params(
        self,
        operation,
        parameters,
        placeholder=re.compile(r"%\((\w+)\)s", re.IGNORECASE),
    ):
        ordered_parameters = []

        def repl(m):
            name = m.group(1)
            value = parameters[name]
            if isinstance(value, self._need_to_be_pickled):
                value = pickle.dumps(value, 4).decode("latin1")
            ordered_parameters.append(value)
            return "?"

        operation = placeholder.sub(repl, operation)
        return operation, ordered_parameters

    def __update_comment(self, table, col, comment):
        key = table + "," + col
        self.cursor.execute("delete from comments where key=?", [key])
        self.cursor.execute(f"insert into comments values(?, {comment})", [key])

    __create_table = re.compile(
        r"\s*create\s+table\s+`(?P<table>\w+)`", re.IGNORECASE
    ).match

    def __handle_comments(
        self,
        operation,
        alter_table=re.compile(
            r"\s*ALTER\s+TABLE\s+`(?P<table>\w+)`\s+"
            r"SET\s+OPTIONS\(description=(?P<comment>[^)]+)\)",
            re.IGNORECASE,
        ).match,
        options=re.compile(
            r"(?P<prefix>`(?P<col>\w+)`\s+\w+|\))" r"\s+options\((?P<options>[^)]+)\)",
            re.IGNORECASE,
        ),
    ):
        m = self.__create_table(operation)
        if m:
            table_name = m.group("table")

            def repl(m):
                col = m.group("col") or ""
                options = {
                    name.strip().lower(): value.strip()
                    for name, value in (
                        o.split("=") for o in m.group("options").split(",")
                    )
                }

                comment = options.get("description")
                if comment:
                    self.__update_comment(table_name, col, comment)

                return m.group("prefix")

            return options.sub(repl, operation)

        m = alter_table(operation)
        if m:
            table_name = m.group("table")
            comment = m.group("comment")
            self.__update_comment(table_name, "", comment)
            return ""

        return operation

    def __handle_array_types(
        self,
        operation,
        array_type=re.compile(
            r"(?<=[(,])" r"\s*`\w+`\s+\w+<\w+>\s*" r"(?=[,)])", re.IGNORECASE
        ),
    ):
        if self.__create_table(operation):

            def repl(m):
                return m.group(0).replace("<", "_").replace(">", "_")

            return array_type.sub(repl, operation)
        else:
            return operation

    @staticmethod
    def __parse_dateish(type_, value):
        type_ = type_.lower()
        if type_ == "timestamp":
            type_ = "datetime"

        if type_ == "datetime":
            return datetime.datetime.strptime(
                value, "%Y-%m-%d %H:%M:%S.%f" if "." in value else "%Y-%m-%d %H:%M:%S",
            )
        elif type_ == "date":
            return datetime.date(*map(int, value.split("-")))
        elif type_ == "time":
            if "." in value:
                value, micro = value.split(".")
                micro = [micro]
            else:
                micro = []

            return datetime.time(*map(int, value.split(":") + micro))
        else:
            raise AssertionError(type_)  # pragma: NO COVER

    def __handle_problematic_literal_inserts(
        self,
        operation,
        literal_insert_values=re.compile(
            r"\s*(insert\s+into\s+.+\s+values\s*)" r"(\([^)]+\))" r"\s*$", re.IGNORECASE
        ).match,
        bq_dateish=re.compile(
            r"(?<=[[(,])\s*"
            r"(?P<type>date(?:time)?|time(?:stamp)?) (?P<val>'[^']+')"
            r"\s*(?=[]),])",
            re.IGNORECASE,
        ),
        need_to_be_pickled_literal=_need_to_be_pickled + (bytes,),
    ):
        if "?" in operation:
            return operation
        m = literal_insert_values(operation)
        if m:
            prefix, values = m.groups()
            safe_globals = {
                "__builtins__": {
                    "parse_datish": self.__parse_dateish,
                    "true": True,
                    "false": False,
                }
            }

            values = bq_dateish.sub(r"parse_datish('\1', \2)", values)
            values = eval(values[:-1] + ",)", safe_globals)
            values = ",".join(
                map(
                    repr,
                    (
                        (
                            base64.b16encode(pickle.dumps(v, 4)).decode()
                            if isinstance(v, need_to_be_pickled_literal)
                            else v
                        )
                        for v in values
                    ),
                )
            )
            return f"{prefix}({values})"
        else:
            return operation

    def __handle_unnest(
        self, operation, unnest=re.compile(r"UNNEST\(\[ ([^\]]+)? \]\)", re.IGNORECASE),
    ):
        return unnest.sub(r"(\1)", operation)

    def __handle_true_false(self, operation):
        # Older sqlite versions, like those used on the CI servers
        # don't support true and false (as aliases for 1 and 0).
        return operation.replace(" true", " 1").replace(" false", " 0")

    def execute(self, operation, parameters=()):
        self.connection.test_data["execute"].append((operation, parameters))
        operation, types_ = google.cloud.bigquery.dbapi.cursor._extract_types(operation)
        if parameters:
            operation, parameters = self.__convert_params(operation, parameters)
        else:
            operation = operation.replace("%%", "%")

        operation = self.__handle_comments(operation)
        operation = self.__handle_array_types(operation)
        operation = self.__handle_problematic_literal_inserts(operation)
        operation = self.__handle_unnest(operation)
        operation = self.__handle_true_false(operation)

        if operation:
            try:
                self.cursor.execute(operation, parameters)
            except sqlite3.OperationalError as e:  # pragma: NO COVER
                # Help diagnose errors that shouldn't happen.
                # When they do, it's likely due to sqlite versions (environment).
                raise sqlite3.OperationalError(
                    *((operation,) + e.args + (sqlite3.sqlite_version,))
                )

        self.description = self.cursor.description
        self.rowcount = self.cursor.rowcount

    def executemany(self, operation, parameters_list):
        for parameters in parameters_list:
            self.execute(operation, parameters)

    def close(self):
        self.cursor.close()

    def _fix_pickled(self, row):
        if row is None:
            return row

        return [
            (
                pickle.loads(v.encode("latin1"))
                # \x80\x04 is latin-1 encoded prefix for Pickle protocol 4.
                if isinstance(v, str) and v[:2] == "\x80\x04" and v[-1] == "."
                else pickle.loads(base64.b16decode(v))
                # 8004 is base64 encoded prefix for Pickle protocol 4.
                if isinstance(v, str) and v[:4] == "8004" and v[-2:] == "2E"
                else v
            )
            for d, v in zip(self.description, row)
        ]

    def fetchone(self):
        return self._fix_pickled(self.cursor.fetchone())

    def fetchall(self):
        return map(self._fix_pickled, self.cursor)


class attrdict(dict):
    def __setattr__(self, name, val):
        self[name] = val

    def __getattr__(self, name):
        if name not in self:
            self[name] = attrdict()
        return self[name]


class FauxClient:
    def __init__(self, project_id=None, default_query_job_config=None, *args, **kw):

        if project_id is None:
            if default_query_job_config is not None:
                project_id = default_query_job_config.default_dataset.project
            else:
                project_id = "authproj"  # we would still have gotten it from auth.

        self.project = project_id
        self.tables = attrdict()

    @staticmethod
    def _row_dict(row, cursor):
        result = {d[0]: value for d, value in zip(cursor.description, row)}
        return result

    def _get_field(
        self,
        type,
        name=None,
        notnull=None,
        mode=None,
        description=None,
        fields=(),
        columns=None,  # Custom column data provided by tests.
        **_,  # Ignore sqlite PRAGMA data we don't care about.
    ):
        if columns:
            custom = columns.get(name)
            if custom:
                return self._get_field(
                    # We express the kwargs this way to allow custom
                    # values to overrise name, type and nonnull, if
                    # necessary.
                    **dict(name=name, type=type, notnull=notnull, **custom)
                )

        if not mode:
            mode = "REQUIRED" if notnull else "NULLABLE"

        field = google.cloud.bigquery.schema.SchemaField(
            name=name,
            field_type=type,
            mode=mode,
            description=description,
            fields=tuple(self._get_field(**f) for f in fields),
        )

        return field

    def __get_comments(self, cursor, table_name):
        cursor.execute(
            f"select key, comment"
            f" from comments where key like {repr(table_name + '%')}"
        )

        return {key.split(",")[1]: comment for key, comment in cursor}

    def get_table(self, table_ref):
        table_ref = google.cloud.bigquery.table._table_arg_to_table_ref(
            table_ref, self.project
        )
        table_name = table_ref.table_id
        with contextlib.closing(self.connection.connection.cursor()) as cursor:
            cursor.execute(f"select * from sqlite_master where name='{table_name}'")
            rows = list(cursor)
            if rows:
                table_data = self._row_dict(rows[0], cursor)

                comments = self.__get_comments(cursor, table_name)
                table_comment = comments.pop("", None)
                columns = getattr(self.tables, table_name).columns
                for col, comment in comments.items():
                    getattr(columns, col).description = comment

                cursor.execute(f"PRAGMA table_info('{table_name}')")
                schema = [
                    self._get_field(columns=columns, **self._row_dict(row, cursor))
                    for row in cursor
                ]
                table = google.cloud.bigquery.table.Table(table_ref, schema)
                table.description = table_comment
                if table_data["type"] == "view" and table_data["sql"]:
                    table.view_query = table_data["sql"][
                        table_data["sql"].lower().index("select") :
                    ]

                for aname, value in self.tables.get(table_name, {}).items():
                    setattr(table, aname, value)

                return table
            else:
                raise google.api_core.exceptions.NotFound(table_ref)

    def list_datasets(self):
        return [
            google.cloud.bigquery.Dataset("myproject.mydataset"),
            google.cloud.bigquery.Dataset("myproject.yourdataset"),
        ]

    def list_tables(self, dataset):
        with contextlib.closing(self.connection.connection.cursor()) as cursor:
            cursor.execute("select * from sqlite_master")
            return [
                google.cloud.bigquery.table.TableListItem(
                    dict(
                        tableReference=dict(
                            projectId=dataset.project,
                            datasetId=dataset.dataset_id,
                            tableId=row["name"],
                        ),
                        type=row["type"].upper(),
                    )
                )
                for row in (self._row_dict(row, cursor) for row in cursor)
                if row["name"] != "comments"
            ]
