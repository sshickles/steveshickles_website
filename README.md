# Steve Shickles Personal Website

A professional personal website for Steve Shickles, AI Integration Specialist & Technology Executive.

## Architecture

This website is hosted on AWS using:
- **S3** for static website hosting
- **CloudFront** for global content delivery
- **CloudFormation** for infrastructure as code
- **GitHub Actions** for CI/CD

## Deployment

The website automatically deploys to AWS when changes are pushed:
- **dev branch** → Development environment (dev.steveshickles.com)
- **master branch** → Production environment (steveshickles.com)

## Setup Instructions

### Prerequisites
1. AWS Account with appropriate permissions
2. GitHub repository with AWS credentials configured as secrets:
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`

### Initial Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/YOUR_USERNAME/steveshickles_website.git
   cd steveshickles_website
   ```

2. Configure AWS credentials in GitHub:
   - Go to Settings → Secrets and variables → Actions
   - Add `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`

3. Deploy to development:
   ```bash
   git checkout dev
   git push origin dev
   ```

4. Deploy to production:
   ```bash
   git checkout master
   git push origin master
   ```

## Project Structure

```
.
├── index.html              # Main website page
├── error.html              # 404 error page
├── cloudformation/         # AWS infrastructure templates
│   └── s3-static-website.yaml
└── .github/workflows/      # GitHub Actions CI/CD
    ├── deploy-dev.yml
    └── deploy-prod.yml
```

## Making Changes

1. Always work on the `dev` branch first:
   ```bash
   git checkout dev
   # Make your changes
   git add .
   git commit -m "Your commit message"
   git push origin dev
   ```

2. Test changes in the development environment

3. Merge to master for production deployment:
   ```bash
   git checkout master
   git merge dev
   git push origin master
   ```

## CloudFormation Stacks

The infrastructure creates two separate stacks:
- `steveshickles-website-dev` - Development environment
- `steveshickles-website-prod` - Production environment

Each stack includes:
- S3 bucket for website hosting
- CloudFront distribution for CDN
- Appropriate bucket policies and configurations

## URLs

After deployment, your sites will be available at:
- Development: CloudFront URL (shown in GitHub Actions output)
- Production: CloudFront URL (shown in GitHub Actions output)

To use custom domains, you'll need to:
1. Configure Route 53 or your DNS provider
2. Update the CloudFormation template to include ACM certificates
3. Configure CloudFront to use your custom domain

## Security Notes

- Never commit AWS credentials to the repository
- Use IAM roles with minimal required permissions
- CloudFront provides HTTPS by default
- S3 buckets are configured for public read access (required for static hosting)