# Security policy

## Reporting a vulnerability

Please do not open a public issue for security problems. Report them privately through [GitHub's private vulnerability reporting](https://github.com/Rustix-Development/pterodactyl-python-egg/security/advisories/new), or by email to mohamed@rustix.xyz.

Include the egg version, the Python version (Docker image) of the server, whether Multi-Bot Mode is on, your panel version and the steps to reproduce. You'll get a reply as soon as possible, and a fix will be released before the issue is made public.

## Supported versions

Only the latest egg release and the current Docker images get security fixes.

## What counts

The Multi-Bot web panel is the main thing exposed to the network. Anything that gets past
its login, runs commands through it, or leaks a bot's `.env` (tokens) to another bot or
to the browser is a security issue. The panel is meant to sit on the server's own port;
put HTTPS in front of it (a reverse proxy or Cloudflare) if you open it to the internet.
