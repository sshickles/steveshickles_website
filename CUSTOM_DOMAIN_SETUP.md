# Custom Domain Setup for steveshickles.com

This guide walks through setting up custom domains for your website using Route 53 and ACM certificates.

## Prerequisites

1. Domain registered (can be with Route 53 or another registrar)
2. AWS CLI configured with appropriate permissions
3. Access to DNS management for your domain

## Step 1: Create or Import Route 53 Hosted Zone

### Option A: If your domain is registered with Route 53
Your hosted zone should already exist. Find the Hosted Zone ID:
```bash
aws route53 list-hosted-zones --query "HostedZones[?Name=='steveshickles.com.'].Id" --output text
```

### Option B: If your domain is registered elsewhere
1. Create a hosted zone:
```bash
aws route53 create-hosted-zone --name steveshickles.com --caller-reference $(date +%s)
```

2. Note the nameservers from the output and update them with your domain registrar.

## Step 2: Request ACM Certificate

**Important**: The certificate MUST be created in us-east-1 region for CloudFront.

```bash
# Deploy the certificate stack
aws cloudformation create-stack \
  --stack-name steveshickles-acm-certificate \
  --template-body file://cloudformation/acm-certificate.yaml \
  --parameters ParameterKey=DomainName,ParameterValue=steveshickles.com \
               ParameterKey=HostedZoneId,ParameterValue=YOUR_HOSTED_ZONE_ID \
  --region us-east-1
```

Wait for the certificate to be validated (this can take up to 30 minutes):
```bash
aws cloudformation wait stack-create-complete \
  --stack-name steveshickles-acm-certificate \
  --region us-east-1
```

Get the certificate ARN:
```bash
aws cloudformation describe-stacks \
  --stack-name steveshickles-acm-certificate \
  --region us-east-1 \
  --query 'Stacks[0].Outputs[?OutputKey==`CertificateArn`].OutputValue' \
  --output text
```

## Step 3: Update GitHub Actions Workflows

Update both `.github/workflows/deploy-dev.yml` and `.github/workflows/deploy-prod.yml` to use the new template with custom domain support.

Replace the CloudFormation deployment section with:

```yaml
    - name: Deploy CloudFormation Stack
      run: |
        STACK_NAME="steveshickles-website-${{ github.ref_name == 'master' && 'prod' || 'dev' }}"
        CERTIFICATE_ARN="YOUR_CERTIFICATE_ARN_HERE"
        HOSTED_ZONE_ID="YOUR_HOSTED_ZONE_ID_HERE"
        
        # Check if stack exists
        if aws cloudformation describe-stacks --stack-name $STACK_NAME --region ${{ env.AWS_REGION }} 2>/dev/null; then
          echo "Updating existing stack..."
          aws cloudformation update-stack \
            --stack-name $STACK_NAME \
            --template-body file://cloudformation/s3-static-website-with-domain.yaml \
            --parameters ParameterKey=Environment,ParameterValue=${{ github.ref_name == 'master' && 'prod' || 'dev' }} \
                         ParameterKey=CertificateArn,ParameterValue=$CERTIFICATE_ARN \
                         ParameterKey=HostedZoneId,ParameterValue=$HOSTED_ZONE_ID \
            --capabilities CAPABILITY_IAM \
            --region ${{ env.AWS_REGION }} || true
          
          aws cloudformation wait stack-update-complete \
            --stack-name $STACK_NAME \
            --region ${{ env.AWS_REGION }} || true
        else
          echo "Creating new stack..."
          aws cloudformation create-stack \
            --stack-name $STACK_NAME \
            --template-body file://cloudformation/s3-static-website-with-domain.yaml \
            --parameters ParameterKey=Environment,ParameterValue=${{ github.ref_name == 'master' && 'prod' || 'dev' }} \
                         ParameterKey=CertificateArn,ParameterValue=$CERTIFICATE_ARN \
                         ParameterKey=HostedZoneId,ParameterValue=$HOSTED_ZONE_ID \
            --capabilities CAPABILITY_IAM \
            --region ${{ env.AWS_REGION }}
          
          aws cloudformation wait stack-create-complete \
            --stack-name $STACK_NAME \
            --region ${{ env.AWS_REGION }}
        fi
```

## Step 4: Add Secrets to GitHub

Add these as GitHub secrets:
- `CERTIFICATE_ARN` - The ACM certificate ARN from Step 2
- `HOSTED_ZONE_ID` - Your Route 53 hosted zone ID

## Step 5: Deploy

1. Commit and push changes:
```bash
git add .
git commit -m "Add custom domain support"
git push origin dev
```

2. After successful dev deployment, merge to master:
```bash
git checkout master
git merge dev
git push origin master
```

## URLs After Setup

Your sites will be available at:
- Production: https://steveshickles.com and https://www.steveshickles.com
- Development: https://dev.steveshickles.com

## Troubleshooting

### Certificate Validation Issues
- Ensure the hosted zone ID is correct
- Check that DNS validation records were created
- Verify your domain's nameservers point to Route 53 (if using Route 53)

### CloudFront Distribution Errors
- Certificate must be in us-east-1
- Allow up to 15 minutes for CloudFront distribution changes to propagate
- Check CloudFormation events for detailed error messages

### DNS Not Resolving
- Verify Route 53 records were created
- DNS propagation can take up to 48 hours
- Use `dig` or `nslookup` to verify DNS records:
  ```bash
  dig steveshickles.com
  dig dev.steveshickles.com
  ```

## Manual Deployment (Optional)

If you prefer to deploy manually instead of using GitHub Actions:

```bash
# Deploy production
aws cloudformation deploy \
  --stack-name steveshickles-website-prod \
  --template-file cloudformation/s3-static-website-with-domain.yaml \
  --parameter-overrides \
    Environment=prod \
    CertificateArn=YOUR_CERTIFICATE_ARN \
    HostedZoneId=YOUR_HOSTED_ZONE_ID \
  --region us-east-1

# Sync files
aws s3 sync . s3://steveshickles.com/ \
  --exclude ".git/*" \
  --exclude ".github/*" \
  --exclude "cloudformation/*" \
  --exclude "*.md" \
  --delete

# Invalidate CloudFront
DIST_ID=$(aws cloudformation describe-stacks \
  --stack-name steveshickles-website-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`CloudFrontDistributionId`].OutputValue' \
  --output text)

aws cloudfront create-invalidation \
  --distribution-id $DIST_ID \
  --paths "/*"
```