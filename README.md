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
    └── deploy-github-pages.yml
```

## Development Workflow

1. **Make changes on dev branch**:
   ```bash
   git checkout dev
   # Make your changes
   git add .
   git commit -m "Your commit message"
   git push origin dev
   ```

2. **Deploy to production**:
   ```bash
   git checkout master
   git merge dev
   git push origin master
   ```

The GitHub Actions workflow automatically deploys to GitHub Pages when you push to master.

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

To update content, edit `index.html` and follow the development workflow above. Changes pushed to master will automatically deploy within a few minutes.