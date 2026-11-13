# GitHub Pages Setup Guide

This guide explains how to host your website on GitHub Pages instead of AWS.

## Benefits of GitHub Pages

- **Free hosting** for static websites
- **Automatic SSL certificates** via Let's Encrypt
- **Simple deployment** - just push to master branch
- **Custom domain support** included
- **No AWS costs or complexity**

## Setup Instructions

### 1. Enable GitHub Pages

1. Go to your repository: https://github.com/sshickles/steveshickles_website
2. Click on **Settings** → **Pages** (in the left sidebar)
3. Under **Source**, select:
   - Source: **Deploy from a branch**
   - Branch: **master**
   - Folder: **/ (root)**
4. Click **Save**

### 2. Custom Domain Setup (Optional)

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

2. **Verify Domain** in GitHub:
   - Go to Settings → Pages
   - Under "Custom domain", enter: `steveshickles.com`
   - Click Save
   - Check "Enforce HTTPS" (may take a few minutes to be available)

### 3. Deployment

The `static.yml` workflow deploys on pushes to `master` or manual workflow
dispatch. The default branch is `dev`; merging a PR into `dev` does not deploy.

## URLs

Once GitHub Pages is enabled:
- **GitHub Pages URL**: https://sshickles.github.io/steveshickles_website/
- **Custom Domain** (after DNS propagation): https://steveshickles.com

## Troubleshooting

### Site not appearing
- GitHub Pages can take up to 10 minutes for initial deployment
- Check the Actions tab for deployment status
- Verify Pages is enabled in Settings

### Custom domain not working
- DNS propagation can take up to 48 hours
- Verify DNS records with: `dig steveshickles.com`
- Ensure CNAME file exists in repository root
- Check "Enforce HTTPS" in GitHub Pages settings

### 404 errors
- Ensure index.html is in the repository root
- Check that the master branch is selected as source
- Verify the workflow completed successfully
