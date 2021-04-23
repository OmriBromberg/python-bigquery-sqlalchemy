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

import pytest
from sqlalchemy import and_
from sqlalchemy.testing.assertions import eq_
from sqlalchemy.testing.suite import *
from sqlalchemy.testing.suite import (
    DateTest as _DateTest,
    DateTimeTest as _DateTimeTest,
    TimeTest as TimeTest,
    DateTimeCoercedToDateTimeTest as _DateTimeCoercedToDateTimeTest,
    DateTimeMicrosecondsTest as _DateTimeMicrosecondsTest,
    TimeMicrosecondsTest as _TimeMicrosecondsTest,
    TextTest as TextTest,
    UnicodeTextTest as UnicodeTextTest,
    UnicodeVarcharTest as UnicodeVarcharTest,
    InsertBehaviorTest as _InsertBehaviorTest,
    ExistsTest as _ExistsTest,
    NumericTest as _NumericTest,
    LimitOffsetTest as _LimitOffsetTest,
    RowFetchTest as _RowFetchTest,
    SimpleUpdateDeleteTest as _SimpleUpdateDeleteTest,
    CTETest as _CTETest,
)

# Quotes aren't allowed in BigQuery table names.
del QuotedNameArgumentTest


class BQCantGuessTypeForComplexQueries(_DateTest):
    # Like:

    # SELECT `date_table`.`id` AS `date_table_id`
    # FROM `date_table`
    # WHERE CASE WHEN (@`foo` IS NOT NULL)
    #       THEN @`foo` ELSE `date_table`.`date_data` END = `date_table`.`date_data`

    # bind_expression is the hook to fix this n the BQ client side.

    @pytest.mark.skip()
    def test_null_bound_comparison(cls):
        pass


class DateTest(BQCantGuessTypeForComplexQueries, _DateTest):
    pass


class DateTimeTest(BQCantGuessTypeForComplexQueries, _DateTimeTest):
    pass


class TimeTest(BQCantGuessTypeForComplexQueries, TimeTest):
    pass


class DateTimeCoercedToDateTimeTest(BQCantGuessTypeForComplexQueries, _DateTimeCoercedToDateTimeTest):
    pass


class DateTimeMicrosecondsTest(BQCantGuessTypeForComplexQueries, _DateTimeMicrosecondsTest):
    pass


class TimeMicrosecondsTest(BQCantGuessTypeForComplexQueries, _TimeMicrosecondsTest):
    pass


class InsertBehaviorTest(_InsertBehaviorTest):

    @pytest.mark.skip()
    def test_insert_from_select_autoinc(cls):
        """BQ has no autoinc and client-side defaults can't work for select."""


class ExistsTest(_ExistsTest):
    """
    Override

    Becaise Bigquery requires FROM when there's a WHERE and
    the base tests didn't do provide a FROM.
    """

    def test_select_exists(self, connection):
        stuff = self.tables.stuff
        eq_(
            connection.execute(
                select([stuff.c.id]).where(
                    and_(
                        stuff.c.id == 1,
                        exists().where(stuff.c.data == "some data"),
                    )
                )
            ).fetchall(),
            [(1,)],
        )

    def test_select_exists_false(self, connection):
        stuff = self.tables.stuff
        eq_(
            connection.execute(
                select([stuff.c.id]).where(
                    exists().where(stuff.c.data == "no data")
                )
            ).fetchall(),
            [],
        )


class LimitOffsetTest(_LimitOffsetTest):

    @pytest.mark.skip()
    def test_simple_offset(self):
        """BigQuery doesn't allow an offset without a limit."""

    test_bound_offset = test_simple_offset


# This test requires features (indexes, primary keys, etc., that BigQuery doesn't have.
del LongNameBlowoutTest


class SimpleUpdateDeleteTest(_SimpleUpdateDeleteTest):
    """The base tests fail if operations return rows for some reason."""

    def test_update(self):
        t = self.tables.plain_pk
        r = config.db.execute(t.update().where(t.c.id == 2), data="d2_new")
        assert not r.is_insert
        #assert not r.returns_rows

        eq_(
            config.db.execute(t.select().order_by(t.c.id)).fetchall(),
            [(1, "d1"), (2, "d2_new"), (3, "d3")],
        )

    def test_delete(self):
        t = self.tables.plain_pk
        r = config.db.execute(t.delete().where(t.c.id == 2))
        assert not r.is_insert
        #assert not r.returns_rows
        eq_(
            config.db.execute(t.select().order_by(t.c.id)).fetchall(),
            [(1, "d1"), (3, "d3")],
        )


class CTETest(_CTETest):

    @pytest.mark.skip("Can't use CTEs with insert")
    def test_insert_from_select_round_trip(self):
        pass

    @pytest.mark.skip("Recusive CTEs aren't supported.")
    def test_select_recursive_round_trip(self):
        pass
