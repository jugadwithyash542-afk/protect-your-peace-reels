import type { Request, Response, NextFunction } from 'express';
import { getDb, getUnifiedApiKey } from '../db/index.js';
import crypto from 'crypto';

function timingSafeStringEqual(provided: string, expected: string): boolean {
  const a = Buffer.from(provided);
  const b = Buffer.from(expected);
  const compareA = a.length === b.length ? a : Buffer.alloc(b.length);
  return crypto.timingSafeEqual(compareA, b) && a.length === b.length;
}

export function adminAuth(req: Request, res: Response, next: NextFunction) {
  // Bypass in test environments to keep tests clean
  if (process.env.NODE_ENV === 'test') {
    next();
    return;
  }

  // Extract token from request
  const token = req.headers.authorization?.replace(/^Bearer\s+/i, '');

  let unifiedKey: string;
  try {
    unifiedKey = getUnifiedApiKey();
  } catch (err) {
    // If the database is not initialized yet, allow request to fail or return 500
    res.status(500).json({ error: { message: 'Database not initialized.' } });
    return;
  }

  if (!token || !timingSafeStringEqual(token, unifiedKey)) {
    res.status(401).json({
      error: { message: 'Unauthorized. Invalid or missing admin API key.', type: 'authentication_error' },
    });
    return;
  }

  next();
}
