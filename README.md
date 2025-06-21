# LinkGuard Telegram Bot

LinkGuard Bot is a Python-based Telegram bot designed to automate the generation and posting of temporary invite links from specified source Telegram groups/channels to a designated target channel. This helps in managing access by providing time-limited and user-limited invite links that refresh automatically.

Key Features:
- **Automatic Invite Link Regeneration:** Periodically creates new invite links for source chats.
- **Configurable Sources & Target:** Set multiple source groups/channels and one target channel.
- **Source Aliases:** Assign custom names to source chats for clearer display in messages.
- **Customizable Timer & User Limit:** Define how long links are valid and how many users can join per link.
- **Flexible Message Template:** Use HTML formatting and a `{links_list}` placeholder to customize the announcement message.
- **Update Modes:** Choose to either edit the last message with the new link or delete the old message and post a new one.
- **Owner-Only Controls:** Bot commands are restricted to the designated owner.

## Getting Started

These instructions will get you a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

What things you need to install the software and how to install them:

- Python 3.x
- pip (Python package installer)

You can download Python from [python.org](https://www.python.org/downloads/). Pip usually comes with Python installations.

### Installing

A step-by-step series of examples that tell you how to get a development environment running:

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd <repository-directory>
    ```

2.  **Create a virtual environment (recommended):**
    ```bash
    python -m venv venv
    ```
    Activate the virtual environment:
    - On Windows:
      ```bash
      .\venv\Scripts\activate
      ```
    - On macOS and Linux:
      ```bash
      source venv/bin/activate
      ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set up environment variables:**
    The bot requires a Telegram Bot Token and your Telegram User ID to function.
    - Create a `.env` file in the root directory of the project:
      ```bash
      touch .env
      ```
    - Add your bot token and owner ID to the `.env` file like this:
      ```
      BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
      OWNER_ID="YOUR_TELEGRAM_USER_ID"
      ```
    - You can get a `BOT_TOKEN` by talking to [BotFather](https://t.me/BotFather) on Telegram.
    - You can find your `OWNER_ID` by talking to a bot like [userinfobot](https://t.me/userinfobot) on Telegram.

## Local Development

How to run the project locally.

-   **Run the application:**
    ```bash
    python main.py
    ```

## Deployment to Railway

Steps to deploy this project to Railway.

1.  **Sign up or Log in to Railway:**
    Go to [railway.app](https://railway.app/) and create an account or log in if you already have one.

2.  **Create a New Project:**
    - Click on "New Project".
    - Choose "Deploy from GitHub repo".
    - Select your repository that contains this project. Railway will automatically detect the `requirements.txt` and suggest a Python build.

3.  **Configure Build and Start Commands:**
    - Railway will likely auto-detect this as a Python project.
    - **Build Command:** The default `pip install -r requirements.txt` (or similar detected by Railway) is correct.
    - **Start Command:** Set this to `python main.py`. This command will run your bot and start polling for updates.

4.  **Add Environment Variables on Railway:**
    - Go to your project settings in Railway.
    - Navigate to the "Variables" tab.
    - Add the following environment variables:
        - `BOT_TOKEN`: Your Telegram Bot Token.
        - `OWNER_ID`: Your Telegram User ID.
    - These are the same variables you set up in the `.env` file for local development. Railway does not use the `.env` file directly for deployed services.
    - *Note: This bot uses polling and does not run as a web server, so the `PORT` variable automatically provided by Railway is not used by this application.*

5.  **Deploy:**
    Railway will automatically deploy your application upon pushing to the connected GitHub branch (usually `main` or `master`). You can also trigger manual deploys from the Railway dashboard.

6.  **Accessing your bot:**
    Once deployed, the bot will be running and connected to Telegram. You can interact with it by sending commands to it in your Telegram client, provided you are the `OWNER_ID`. There is no public URL for the bot itself; interaction is solely through Telegram.

## Usage

This bot is controlled via commands sent to it on Telegram by the designated `OWNER_ID`.

### Interacting with the Bot

1.  **Start the Bot:** Ensure the bot is running either locally or deployed on Railway.
2.  **Open a Chat with Your Bot:** Find your bot on Telegram.
3.  **Use Commands:** As the bot owner, you can use the following commands:

    *   `/start` or `/help`: Displays a detailed overview of all available commands and their usage.
    *   `/set_channels <target_channel_id_or_@username> <source1_id_or_@username>[:"Optional Alias"] [source2...]`:
        *   Sets the target channel where invite links will be posted.
        *   Sets one or more source groups/channels from which invite links will be generated.
        *   Source channels can have optional aliases (e.g., `source_id:"My Group"`). If an alias contains spaces, it must be enclosed in double quotes.
        *   The bot must be an administrator in the target channel (to post and delete messages) and in all source groups/channels (to create invite links).
        *   Example: `/set_channels @my_link_channel @source_group_1:"Main Chat" -1001234567890:"Private Group"`
    *   `/set_timer <minutes>`:
        *   Sets the interval (in minutes) at which new invite links are generated and posted. Minimum 1 minute.
    *   `/set_limit <number>`:
        *   Sets the maximum number of users that can use each generated invite link. Minimum 1 user.
    *   `/set_template <HTML text>`:
        *   Customizes the message posted by the bot.
        *   Supports basic HTML tags (bold, italic, underline, strikethrough, code, pre, links).
        *   Use `{links_list}` as a placeholder. This will be replaced by a list of generated invite links, formatted with their aliases or IDs.
        *   Example: `/set_template <b>New Links Available!</b>\n{links_list}\nJoin before they expire.`
    *   `/start_posting`:
        *   Activates the automatic link generation and posting job based on the current configuration.
        *   The first post is made immediately, and subsequent posts follow the schedule set by `/set_timer`.
    *   `/stop_posting`:
        *   Deactivates the auto-posting job.
    *   `/toggle_update_mode`:
        *   Switches how the bot updates the message in the target channel.
        *   **EDIT Mode:** The bot attempts to edit its last sent message with the new links.
        *   **REPLACE Mode:** The bot deletes its old message and sends a new one.
    *   `/get_config`:
        *   Displays the current settings of the bot, including source/target channels, timer, limit, template, job status, and update mode.

### How to Change or Add Features (Code Modifications)

The bot is a single Python script (`main.py`). To modify or extend its functionality:

1.  **Understanding the Code:**
    *   The bot uses the `python-telegram-bot` library. Familiarize yourself with its [documentation](https://docs.python-telegram-bot.org/) if you plan significant changes.
    *   Configuration is stored in a global dictionary `CONFIG`.
    *   Bot commands are defined as functions (e.g., `start`, `set_channels`) and registered with `CommandHandler`.
    *   The core logic for generating and posting links is in `generate_invite_link_for_chat`, `generate_all_invite_links`, `post_new_link`, and the job scheduler.

2.  **Making Changes:**
    *   **Modify existing behavior:** Edit the relevant functions in `main.py`. For example, to change how links are formatted, you might adjust the `post_new_link` function.
    *   **Add new commands:**
        1.  Define a new asynchronous function that takes `update: Update` and `context: ContextTypes.DEFAULT_TYPE` as arguments.
        2.  Implement the command logic within this function.
        3.  Register the new command in the `main()` function using `app.add_handler(CommandHandler("your_new_command", your_new_function))`.
        4.  Consider adding the `@owner_only` decorator if the command should be restricted.
    *   **Change data handling:** If you want to store configuration differently (e.g., in a database instead of the in-memory `CONFIG` dictionary), you'll need to modify how settings are read and written throughout the script.

3.  **Dependencies:**
    *   If your changes require new Python packages, add them to `requirements.txt`.
    *   Then, reinstall dependencies in your virtual environment:
        ```bash
        pip install -r requirements.txt
        ```

4.  **Testing:**
    *   Test your changes thoroughly by running the bot locally and interacting with it on Telegram.

5.  **Deployment:**
    *   Once you're satisfied, commit your changes and push them to your GitHub repository.
    *   If Railway is configured for auto-deploys from your branch, it will automatically pick up the changes and redeploy the bot.

---

*This README provides guidance for using and modifying the LinkGuard Bot.*
