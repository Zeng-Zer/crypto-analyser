# Data type

- Id : int, primary key, serial
- Title : text, not null,
- Description : TEXT
- Link : TEXT,  not null, unique
- Date : TIMESTAMPTZ
- Source : TEXT, not null
- Category : TEXT,not null
- Tickers : TEXT [], not null
- Combo : TEXT, GENERATED ALWAYS AS (title || '	' || COALESCE(description, '	'))  STORED	
- Research : tsvector(to_tsvector('English', 'GENERATED ALWAYS AS (title || '	' || COALESCE(description, '	')')) STORED
- AI : vector(1536)

# Documentation

**
 
 id        : afin de donner une identité unique en donnant un numéro de manière automatique 		       pour chaque nouvel news
 Title     : le titre est obligatoire
 Description : Certain news ne possède pas de description dans l'API
 Link      : toujours avoir le lien afin de vérifier la source et se documenter 
 Date      : Afin de s'adapter au fuseau horaire de la France
 Source    : Obligatoire pour vérifier l'info
 Catégorie : obligatoire pour mieux classer les articles
 Tickers   : créer une liste avec TEXT[] pour mieux filtrer les articles
 Combo     : " GENERATED ALWAYS AS (....) permet de générer automatiquement un modele 			     d'affichage, " || " permet de regrouper , COALESCE ('nom_colonne',                             	     'message_erreur') permet de remplacer la valeur si NUL et STORED pour 	 
	     indexer et évite la  répétition
 Research  : tsvector fonction qui permet de prêt macher les mots afin d'obtenir des mots clés 		     facilitant la recherche, on saisi la langue et la combinaison.
 AI      : pour le embidding, le script python s'en charge
  
**

# Schema structure

**

CREATE DATABASE Crypto_analyse;
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE crypto_news(
ALTER TABLE crypto_news ADD COLUMN id SERIAL PRIMARY KEY,
ALTER TABLE crypto_news ADD COLUMN Title TEXT NOT NULL,
ALTER TABLE crypto_news ADD COLUMN Description TEXT,
ALTER TABLE crypto_news ADD COLUMN Link TEXT NOT NULL UNIQUE,
ALTER TABLE crypto_news ADD COLUMN Date_pub TIMESTAMPTZ,
ALTER TABLE crypto_news ADD COLUMN Source TEXT NOT NULL,
ALTER TABLE crypto_news ADD COLUMN Category TEXT NOT NULL,
ALTER TABLE crypto_news ADD COLUMN Tickers TEXT[] NOT NULL,
ALTER TABLE crypto_news ADD COLUMN Combo TEXT GENERATED ALWAYS AS (Title || ' ' || COALESCE(Description, '' )) STORED,
ALTER TABLE crypto_news ADD COLUMN Research tsvector GENERATED ALWAYS AS (to_tsvector('english', Title || ' ' || COALESCE(Description, ''))) STORED,
ALTER TABLE crypto_news ADD COLUMN AI vector(1536),
);

**
