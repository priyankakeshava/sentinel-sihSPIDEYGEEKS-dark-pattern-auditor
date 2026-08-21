# MySQL Setup (dont refer as shifted to postgress)

## Easiest team setup

Install Docker Desktop, then from the project folder run:

    docker compose up -d

This starts MySQL on port 3306 with:

Database: sentinel
User: sentinel
Password: sentinel

The backend defaults to:

    mysql+pymysql://sentinel:sentinel@127.0.0.1:3306/sentinel

## Without Docker

Create a MySQL database named `sentinel`, create the `sentinel` user, and set:

    DATABASE_URL=mysql+pymysql://sentinel:YOUR_PASSWORD@127.0.0.1:3306/sentinel

The FastAPI application creates the required tables automatically.

## If MySQL is unavailable

The backend automatically falls back to a local SQLite database. This is useful during development, but the intended architecture for the PPT is MySQL.
