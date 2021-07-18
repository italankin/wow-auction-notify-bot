# WoW Auction Notifier Bot

The bot gathers prices from WoW auctions (EU region only) and sends notifications to subscribers.

## Setup

### Credentials

1. Generate Telegram bot token: https://t.me/BotFather
2. Obtain Battle.net credentials: https://develop.battle.net/access/clients/create

###

|Parameter|Description|
|---|---|
|TELEGRAM_BOT_TOKEN|Telegram bot token|
|DATABASE|Path to SQLite database file|
|BNET_CLIENT_ID|Battle.net client ID|
|BNET_CLIENT_SECRET|Battle.net client secret|
|MAX_NOTIFICATIONS|Maximum number of notifications for one user (does not apply to admin users, see `users` table)|

## Docker

### 1. Build image

```shell
$ docker build -t wowauctionnotifier .
```

### 2. Create volume

```shell
$ docker volume create wowauctionnotifier-data
```

### 3. Create env file

Create `.env` file with your parameters:

```
TELEGRAM_BOT_TOKEN=<telegram-bot-token>
DATABASE=/database/0.db
BNET_CLIENT_ID=<battle-net-client-id>
BNET_CLIENT_SECRET=<battle-net-client-secret>
```

### 4. Run image

```shell
$ docker run --rm -d --env-file .env -v wowauctionnotifier-data:/database wowauctionnotifier
```
