#!/bin/bash

echo "Creating table in the database...""
DB_URL=$(grep "^DATABASE_URL=" .env | cut -d '=' -f 2-)
psql "$DB_URL" -f sql/news_schema.sql
echo "Finished."
