import sys
from src.bot import bot
from src.config import config


def main():
    try:
        config.validate_discord()
        bot.run(config.DISCORD_TOKEN)
    except ValueError as e:
        print(f"Configuration Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Fatal Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
