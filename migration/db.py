from enum import Enum
from typing import TypedDict
from urllib.parse import quote_plus

import sqlalchemy


class Dialect(Enum):
    POSTGRES = 'postgresql'


class DBParams(TypedDict):
    host: str
    port: str
    name: str
    user: str
    password: str


class DB:
    engine: sqlalchemy.engine.Engine
    connection: sqlalchemy.engine.Connection | None

    def __init__(self, dialect: Dialect, params: DBParams):
        params['password'] = quote_plus(params['password'])
        core_string = '{user}:{password}@{host}:{port}/{name}'.format(**params)
        self.engine = sqlalchemy.create_engine(f'{dialect.value}://{core_string}')

    def get_connection(self) -> sqlalchemy.engine.Connection:
        if self.connection is None:
            self.connection = self.engine.connect()
        return self.connection
    
    def close_connection(self) -> None:
        if self.connection is not None:
            self.connection.close()

    def __enter__(self):
        self.connection = self.engine.connect()

    def __exit__(self, *args, **kwargs):
        self.close_connection()
        self.engine.dispose()
