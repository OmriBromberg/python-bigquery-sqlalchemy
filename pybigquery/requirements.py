import sqlalchemy.testing.requirements
import sqlalchemy.testing.exclusions

supported = sqlalchemy.testing.exclusions.open
unsupported = sqlalchemy.testing.exclusions.closed

class Requirements(sqlalchemy.testing.requirements.SuiteRequirements):

    @property
    def index_reflection(self):
        return unsupported()

    @property
    def indexes_with_ascdesc(self):
        """target database supports CREATE INDEX with per-column ASC/DESC."""
        return unsupported()

    @property
    def unique_constraint_reflection(self):
        """target dialect supports reflection of unique constraints"""
        return unsupported()

    @property
    def autoincrement_insert(self):
        """target platform generates new surrogate integer primary key values
        when insert() is executed, excluding the pk column."""
        return unsupported()

    @property
    def primary_key_constraint_reflection(self):
        return unsupported()

    @property
    def foreign_keys(self):
        """Target database must support foreign keys."""

        return unsupported()

    @property
    def foreign_key_constraint_reflection(self):
        return unsupported()

    @property
    def on_update_cascade(self):
        """target database must support ON UPDATE..CASCADE behavior in
        foreign keys."""

        return unsupported()

    @property
    def named_constraints(self):
        """target database must support names for constraints."""

        return unsupported()

    @property
    def temp_table_reflection(self):
        return unsupported()

    @property
    def temporary_tables(self):
        """target database supports temporary tables"""
        return unsupported()

    @property
    def table_reflection(self):
        # This includes round-trip type conversions, which would fail,
        # because BigQuery has less precise types.
        return unsupported()

    @property
    def duplicate_key_raises_integrity_error(self):
        """target dialect raises IntegrityError when reporting an INSERT
        with a primary key violation.  (hint: it should)

        """
        return unsupported()