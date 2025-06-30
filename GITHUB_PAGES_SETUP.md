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

The site will automatically deploy when you push to the master branch:

```bash
# Make changes on dev branch
git checkout dev
# ... make your changes ...
git add .
git commit -m "Your changes"
git push origin dev

# Merge to master to deploy
git checkout master
git merge dev
git push origin master
```

## Removing AWS Resources (Optional)

If you no longer need the AWS setup:

1. **Delete CloudFormation Stacks**:
   ```bash
   # Delete dev stack
   aws cloudformation delete-stack --stack-name steveshickles-website-dev --region us-east-1

   # Delete prod stack
   aws cloudformation delete-stack --stack-name steveshickles-website-prod --region us-east-1

   # Delete certificate stack (if created)
   aws cloudformation delete-stack --stack-name steveshickles-acm-certificate --region us-east-1
   ```

2. **Remove AWS GitHub Secrets**:
   - Go to Settings → Secrets and variables → Actions
   - Delete `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`
   - Delete `CERTIFICATE_ARN` and `HOSTED_ZONE_ID` (if added)

3. **Remove AWS-related files** (optional):
   ```bash
   git rm -r cloudformation/
   git rm .github/workflows/deploy-dev.yml
   git rm .github/workflows/deploy-prod.yml
   git rm CUSTOM_DOMAIN_SETUP.md
   git commit -m "Remove AWS infrastructure files"
   git push origin dev
   ```

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

## Development Workflow

1. **Development**: Work on the `dev` branch
2. **Testing**: Push to `dev` to test changes locally
3. **Production**: Merge to `master` to deploy to GitHub Pages

The GitHub Actions workflow will automatically deploy to GitHub Pages whenever you push to master.