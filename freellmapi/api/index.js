import '../server/dist/env.js';
import { createApp } from '../server/dist/app.js';
import { initDb } from '../server/dist/db/index.js';

// Initialize SQLite database (runs seeding, handles Vercel /tmp path automatically)
initDb();

const app = createApp();

export default app;
