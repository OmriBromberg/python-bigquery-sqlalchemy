import datetime
from decimal import Decimal

import pytest
import sqlalchemy

import pybigquery.sqlalchemy_bigquery


def test_labels_not_forced(faux_conn):
    metadata = sqlalchemy.MetaData()
    table = sqlalchemy.Table(
        "some_table", metadata, sqlalchemy.Column("id", sqlalchemy.Integer)
    )
    metadata.create_all(faux_conn.engine)
    result = faux_conn.execute(sqlalchemy.select([table.c.id]))
    assert result.keys() == ["id"]  # Look! Just the column name!


def dtrepr(v):
    return f"{v.__class__.__name__.upper()} {repr(str(v))}"


@pytest.mark.parametrize(
    "type_,val,btype,vrep",
    [
        (sqlalchemy.String, "myString", "STRING", repr),
        (sqlalchemy.Text, "myText", "STRING", repr),
        (sqlalchemy.Unicode, "myUnicode", "STRING", repr),
        (sqlalchemy.UnicodeText, "myUnicodeText", "STRING", repr),
        (sqlalchemy.Integer, 424242, "INT64", repr),
        (sqlalchemy.SmallInteger, 42, "INT64", repr),
        (sqlalchemy.BigInteger, 1 << 60, "INT64", repr),
        (sqlalchemy.Numeric, Decimal(42), "NUMERIC", str),
        (sqlalchemy.Float, 4.2, "FLOAT64", repr),
        (
            sqlalchemy.DateTime,
            datetime.datetime(2021, 2, 3, 4, 5, 6, 123456),
            "DATETIME",
            dtrepr,
        ),
        (sqlalchemy.Date, datetime.date(2021, 2, 3), "DATE", dtrepr),
        (sqlalchemy.Time, datetime.time(4, 5, 6, 123456), "TIME", dtrepr),
        (sqlalchemy.Boolean, True, "BOOL", "true"),
        (sqlalchemy.REAL, 1.42, "FLOAT64", repr),
        (sqlalchemy.FLOAT, 0.42, "FLOAT64", repr),
        (sqlalchemy.NUMERIC, Decimal(4.25), "NUMERIC", str),
        (sqlalchemy.DECIMAL, Decimal(0.25), "NUMERIC", str),
        (sqlalchemy.INTEGER, 434343, "INT64", repr),
        (sqlalchemy.INT, 444444, "INT64", repr),
        (sqlalchemy.SMALLINT, 43, "INT64", repr),
        (sqlalchemy.BIGINT, 1 << 61, "INT64", repr),
        (
            sqlalchemy.TIMESTAMP,
            datetime.datetime(2021, 2, 3, 4, 5, 7, 123456),
            "TIMESTAMP",
            lambda v: f"TIMESTAMP {repr(str(v))}",
        ),
        (
            sqlalchemy.DATETIME,
            datetime.datetime(2021, 2, 3, 4, 5, 8, 123456),
            "DATETIME",
            dtrepr,
        ),
        (sqlalchemy.DATE, datetime.date(2021, 2, 4), "DATE", dtrepr),
        (sqlalchemy.TIME, datetime.time(4, 5, 7, 123456), "TIME", dtrepr),
        (sqlalchemy.TEXT, "myTEXT", "STRING", repr),
        (sqlalchemy.VARCHAR, "myVARCHAR", "STRING", repr),
        (sqlalchemy.NVARCHAR, "myNVARCHAR", "STRING", repr),
        (sqlalchemy.CHAR, "myCHAR", "STRING", repr),
        (sqlalchemy.NCHAR, "myNCHAR", "STRING", repr),
        (sqlalchemy.BINARY, b"myBINARY", "BYTES", repr),
        (sqlalchemy.VARBINARY, b"myVARBINARY", "BYTES", repr),
        (sqlalchemy.BOOLEAN, False, "BOOL", "false"),
    ],
)
def test_typed_parameters(faux_conn, type_, val, btype, vrep):
    metadata = sqlalchemy.MetaData()
    type_name = type_.__name__
    col_name = "my" + type_name
    table = sqlalchemy.Table("some_table", metadata, sqlalchemy.Column(col_name, type_))
    metadata.create_all(faux_conn.engine)

    assert faux_conn.test_data["execute"].pop()[0].strip() == (
        f"CREATE TABLE `some_table` (\n" f"\t`{col_name}` {btype}\n" f")"
    )

    faux_conn.execute(table.insert().values(**{col_name: val}))

    x = faux_conn.test_data["execute"].pop()
    assert x == (
        f"INSERT INTO `some_table` (`{col_name}`) VALUES (%({col_name}:{btype})s)",
        {col_name: val},
    )

    faux_conn.execute(
        table.insert()
        .values(**{col_name: sqlalchemy.literal(val, type_)})
        .compile(
            dialect=pybigquery.sqlalchemy_bigquery.BigQueryDialect(),
            compile_kwargs=dict(literal_binds=True),
        )
    )

    if not isinstance(vrep, str):
        vrep = vrep(val)

    actual = faux_conn.test_data["execute"].pop()
    assert actual == (f"INSERT INTO `some_table` (`{col_name}`) VALUES ({vrep})", {})

    # We're using sqlite3 as a stub.  It can't store these types:
    if btype in ("DATETIME", "DATE", "TIME", "TIMESTAMP"):
        val = str(val)
    elif btype == "NUMERIC":
        val = float(val)

    assert list(map(list, faux_conn.execute(sqlalchemy.select([table])))) == [[val]] * 2
