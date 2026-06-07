import fs from 'fs';
import path from 'path';
import crypto from 'crypto';

interface ServiceAccountKey {
  project_id: string;
  private_key: string;
  client_email: string;
}

let cachedToken: string | null = null;
let cachedTokenExpiry = 0;
let serviceAccount: ServiceAccountKey | null = null;

// Base64url helper
function base64url(str: string | Buffer): string {
  const buf = typeof str === 'string' ? Buffer.from(str) : str;
  return buf.toString('base64')
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_');
}

export function loadServiceAccount(): ServiceAccountKey {
  if (serviceAccount) return serviceAccount;

  const keyPath = process.env.VERTEX_KEY_FILE;
  if (!keyPath) {
    throw new Error('VERTEX_KEY_FILE environment variable is not defined.');
  }

  const absolutePath = path.isAbsolute(keyPath)
    ? keyPath
    : path.resolve(process.cwd(), keyPath);

  if (!fs.existsSync(absolutePath)) {
    throw new Error(`Vertex service account key file not found at: ${absolutePath}`);
  }

  const content = fs.readFileSync(absolutePath, 'utf8');
  const parsed = JSON.parse(content);
  if (!parsed.project_id || !parsed.private_key || !parsed.client_email) {
    throw new Error('Invalid service account key file. Must contain project_id, private_key, and client_email.');
  }

  serviceAccount = {
    project_id: parsed.project_id,
    private_key: parsed.private_key,
    client_email: parsed.client_email,
  };
  return serviceAccount;
}

export async function getVertexAccessToken(): Promise<{ token: string; projectId: string }> {
  const sa = loadServiceAccount();

  // If token is cached and valid for at least 5 more minutes, return it
  if (cachedToken && Date.now() < cachedTokenExpiry - 300000) {
    return { token: cachedToken, projectId: sa.project_id };
  }

  // Generate JWT assertion
  const now = Math.floor(Date.now() / 1000);
  const expiry = now + 3600; // 1 hour

  const header = {
    alg: 'RS256',
    typ: 'JWT',
  };

  const claimSet = {
    iss: sa.client_email,
    scope: 'https://www.googleapis.com/auth/cloud-platform',
    aud: 'https://oauth2.googleapis.com/token',
    exp: expiry,
    iat: now,
  };

  const encodedHeader = base64url(JSON.stringify(header));
  const encodedClaimSet = base64url(JSON.stringify(claimSet));
  const signatureInput = `${encodedHeader}.${encodedClaimSet}`;

  const signer = crypto.createSign('RSA-SHA256');
  signer.update(signatureInput);
  const signature = signer.sign(sa.private_key);
  const encodedSignature = base64url(signature);

  const assertion = `${signatureInput}.${encodedSignature}`;

  // Call OAuth2 token endpoint
  const response = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body: new URLSearchParams({
      grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
      assertion,
    }),
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`Failed to obtain Google OAuth2 access token: ${response.status} ${errText}`);
  }

  const data = (await response.json()) as { access_token: string; expires_in: number };
  cachedToken = data.access_token;
  cachedTokenExpiry = Date.now() + data.expires_in * 1000;

  return { token: cachedToken, projectId: sa.project_id };
}
