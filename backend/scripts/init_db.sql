-- CompassFXPulse schema. Idempotent: safe to re-run.
-- Run: mysql -u root -p < scripts/init_db.sql

CREATE DATABASE IF NOT EXISTS compass_fx
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE compass_fx;

CREATE TABLE IF NOT EXISTS historicaldata (
    currencytype1 VARCHAR(10) NOT NULL,
    currencytype2 VARCHAR(10) NOT NULL,
    time          DATETIME    NOT NULL,
    rate          DOUBLE      NOT NULL,
    PRIMARY KEY (currencytype1, currencytype2, time),
    INDEX idx_pair_time (currencytype1, currencytype2, time)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS predictdata (
    currencytype1 VARCHAR(10) NOT NULL,
    currencytype2 VARCHAR(10) NOT NULL,
    time          DATETIME    NOT NULL,
    rate          DOUBLE      NOT NULL,
    PRIMARY KEY (currencytype1, currencytype2, time)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS aichat (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    UserMessage     TEXT      NOT NULL,
    AIMessage       LONGTEXT  NOT NULL,
    UserMessageTime DATETIME  NOT NULL,
    AIMessageTime   DATETIME  NOT NULL,
    RecordID        INT       NOT NULL,
    INDEX idx_record (RecordID)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS news (
    id        INT AUTO_INCREMENT PRIMARY KEY,
    source    VARCHAR(50)  NOT NULL,
    currency  VARCHAR(10),
    title     VARCHAR(500) NOT NULL,
    url       VARCHAR(500),
    content   LONGTEXT,
    published DATETIME,
    crawled   DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_currency_time (currency, published)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS currencytypes (
    code  VARCHAR(10) PRIMARY KEY,
    label VARCHAR(50) NOT NULL
) ENGINE=InnoDB;

INSERT IGNORE INTO currencytypes(code, label) VALUES
    ('USD', '美元 (USD)'),
    ('GBP', '英镑 (GBP)'),
    ('EUR', '欧元 (EUR)'),
    ('JPY', '日元 (JPY)'),
    ('HKD', '港币 (HKD)'),
    ('AUD', '澳元 (AUD)');
