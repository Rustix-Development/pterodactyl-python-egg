# Notice

**Python Egg**

Copyright © Mkkbeydoun and contributors, MIT License (see [LICENSE](LICENSE))

## Credits

### Python Universal egg (yajtpg)

- The egg this one replaces: a Python egg with a choice of Python versions as Docker
  images (`quay.io/yajtpg/pterodactyl-images`). No code or images were copied; the idea of
  one egg with a Python version picker comes from it.

### [parkervcp/eggs](https://github.com/parkervcp/eggs)

- Copyright (c) 2018 Michael Parker and Contributors, MIT License
- The Git install logic and the Git Repo Address / Git Branch / Auto Update /
  User Uploaded Files / Git Username / Git Access Token variables.
- License: [licenses/parkervcp-eggs-LICENSE](licenses/parkervcp-eggs-LICENSE)

### Third-party software in the Docker images

- [Python](https://www.python.org) official `python:*-slim` images (PSF License, Debian packages under their own licenses)
- [uv](https://github.com/astral-sh/uv) (MIT / Apache-2.0), [Flask](https://github.com/pallets/flask) (BSD-3-Clause),
  [Waitress](https://github.com/Pylons/waitress) (ZPL 2.1), [psutil](https://github.com/giampaolo/psutil) (BSD-3-Clause),
  [python-dotenv](https://github.com/theskumar/python-dotenv) (BSD-3-Clause), [tini](https://github.com/krallin/tini) (MIT)

## Everything else

Everything else is mine: the Docker images and build workflow, the bot manager and web
panel, the dependency caching, the update check, and the install and start scripts.
