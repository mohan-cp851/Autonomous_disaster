from sqlalchemy import inspect

from utils.database import db


def upgrade_existing_schema():
    if db.engine.dialect.name != 'sqlite':
        return

    columns = {column['name'] for column in inspect(db.engine).get_columns('incidents')}
    additions = {
        'affected_count': 'INTEGER NOT NULL DEFAULT 0',
        'verification_status': "VARCHAR(20) NOT NULL DEFAULT 'Unverified'",
    }

    with db.engine.begin() as connection:
        for column_name, definition in additions.items():
            if column_name not in columns:
                connection.exec_driver_sql(
                    f'ALTER TABLE incidents ADD COLUMN {column_name} {definition}'
                )
