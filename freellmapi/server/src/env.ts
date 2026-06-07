import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

dotenv.config({ path: path.resolve(__dirname, '../../.env') });

// Bypasses TLS issues in local dev environments
process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';

