# Steve Shickles Personal Website

A professional personal website for Steve Shickles, AI Integration Specialist & Technology Executive.

## Hosting

This website is hosted on GitHub Pages with:
- **Free hosting** with automatic SSL
- **Simple deployment** - just push to master branch
- **Custom domain support** included

## Quick Start

1. **Enable GitHub Pages**:
   - Go to Settings → Pages in your repository
   - Select source: Deploy from branch → master → / (root)
   - Click Save

2. **Access your site**:
   - GitHub Pages URL: https://sshickles.github.io/steveshickles_website/
   - Custom domain: https://steveshickles.com (after DNS setup)

## Project Structure

```
.
├── index.html              # Main website page
├── error.html              # 404 error page
├── CNAME                   # Custom domain configuration
└── .github/workflows/      # GitHub Actions for automated deployment
    └── static.yml
```

## Setup and commands

- `./scripts/setup` installs the pinned tools and the Git hooks.
- `./scripts/check` checks the files you changed; `./scripts/check --all` runs everything CI runs.
- `./scripts/test` runs the full test command.

There is no build step. Open `index.html` in a browser to view the site.

`dev` is the default branch. The Pages workflow publishes on pushes to
`master`, so merging a PR into `dev` does not deploy.

## Custom Domain Setup

If you want to use steveshickles.com:

1. **Add DNS Records** with your domain provider:
   ```
   Type: A
   Name: @
   Value: 185.199.108.153
          185.199.109.153
          185.199.110.153
          185.199.111.153

   Type: CNAME
   Name: www
   Value: sshickles.github.io
   ```

2. **Verify in GitHub**:
   - Go to Settings → Pages
   - Custom domain should show: steveshickles.com
   - Check "Enforce HTTPS"

For detailed instructions, see [GITHUB_PAGES_SETUP.md](GITHUB_PAGES_SETUP.md).

## Making Updates

To update content, edit `index.html`. Changes pushed to master deploy automatically within a few minutes.
