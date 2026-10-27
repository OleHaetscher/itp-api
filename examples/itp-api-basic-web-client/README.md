# ITP Client – Circumplex Reference Implementation

A minimal, framework-free web application for a turn-based interaction between the **LASSI model** and a human participant using the **interpersonal circumplex (IPC)**. The left circle shows the behavior of the **Other** person. The right circle lets the **Self** choose a response.

## Requirements

- Web server with **PHP 8.2 or newer**, PHP sessions, and the PHP cURL extension enabled.
- Outgoing HTTPS access to `https://itp-api.uni-muenster.de`.
- A valid API key for the ITP server.
- A modern browser with SVG and Pointer Events. JavaScript must be enabled.

No database, no npm, no Composer, and no JavaScript libraries are required.

## Setup

1. Unpack the archive and copy the `itp-client` directory to your server.
2. If needed, copy `.env.example` to `.env`.
3. Enter the real API key in `itp-client/.env`:

   ```dotenv
   ITP_API_URL=https://itp-api.uni-muenster.de
   ITP_API_KEY=YOUR_REAL_API_KEY
   ```

4. The web server document root must point to `itp-client/public/`, not to the project root.
5. Open `index.html` through the web server.

For local testing with PHP:

```cmd
php -S 127.0.0.1:8080 -t public
```

Then open `http://127.0.0.1:8080` in the browser.

## Main behavior

- The app starts a LASSI interaction with 10 turns.
- Agent A is the model. Agent B is the human participant in IPC space.
- The model starts.
- The browser talks only to `public/api.php`.
- Registration sends a JSON object (`{}`), as required by the ITP API.
- `api.php` keeps the API key, interaction token, session ID, and agent ID on the server.
- Previous behaviors are shown in both circles as fading gray points connected by gray lines.
- The farther back a behavior is in time, the less visible it becomes.
- The most recent behavior in each circle remains colored; the history is gray.

## Files

```text
itp-client/
├── public/
│   ├── index.html
│   ├── style.css
│   ├── api.php
│   └── js/
│       ├── app.js
│       ├── api.js
│       └── circumplex.js
├── .env
├── .env.example
├── .gitignore
└── README.md
```

## JavaScript modules

- **`public/js/app.js`** holds configuration, temporary interaction state, and the turn lifecycle (start, poll, submit, finish). It wires the action buttons to these functions.
- **`public/js/api.js`** wraps same-origin `fetch()` requests to `api.php`, HTTP errors, and request cancellation.
- **`public/js/circumplex.js`** draws both SVG circumplexes and fading behavior paths, handles point selection by pointer/keyboard, and updates UI text and controls.

The application uses native browser ES modules (`type="module"`) and needs no build tooling. Function-level comments are in English. Serve the project over HTTP using PHP rather than opening `index.html` via `file://`.

When upgrading from the single-file version, replace `public/index.html` and deploy the entire `public/js/` directory. The old `public/app.js` is no longer used. **Keep your existing `.env`** in the project root; it is intentionally not included in the release archive.

## Windows note on SSL certificate errors

If PHP cURL reports error 60, PHP does not trust the remote TLS certificate yet. Configure `curl.cainfo` and `openssl.cafile` in `php.ini` and point both to a valid CA bundle such as `cacert.pem` from <https://curl.se/docs/caextract.html>.
