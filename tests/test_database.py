from crypto_analyser.rag import database


def test_initialize_database_executes_schema_and_closes(monkeypatch, tmp_path):
    schema = tmp_path / "schema.sql"
    schema.write_text("SELECT 1;", encoding="utf-8")

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def execute(self, sql):
            self.sql = sql

    class Connection:
        def __init__(self):
            self.cursor_instance = Cursor()
            self.closed = False

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def cursor(self):
            return self.cursor_instance

        def close(self):
            self.closed = True

    connection = Connection()
    monkeypatch.setattr(database.psycopg2, "connect", lambda _: connection)

    database.initialize_database("postgresql://db", schema)

    assert connection.cursor_instance.sql == "SELECT 1;"
    assert connection.closed
