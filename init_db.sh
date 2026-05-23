#!/bin/bash

DB_URL="postgresql://postgres:Postgres@100.107.186.61:5432/crypto_analyser"

echo "Création des tables dans la base de données..."
psql $DB_URL -f news_data/schema.sql
echo "Terminé !"
