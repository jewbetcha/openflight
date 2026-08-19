/**
 * Lightweight Socket.IO mock backend for UI development without Python/hardware.
 *
 * Listens on port 8080 — the same origin Vite's serverOrigin heuristic expects.
 */

import express from 'express';
import { createServer } from 'node:http';
import { Server } from 'socket.io';
import { registerHandlers } from './handlers.js';
import { MockSession } from './session.js';

const PORT = Number(process.env.MOCK_PORT ?? 8080);

const app = express();
app.use(express.json());

app.post('/api/shutdown', (_req, res) => {
  // UI expects 200; do not exit so the mock stays up during UI work.
  res.json({ status: 'shutting_down' });
});

app.get('/health', (_req, res) => {
  res.json({ ok: true, mock: true });
});

const httpServer = createServer(app);
const io = new Server(httpServer, {
  cors: { origin: '*' },
});

const session = new MockSession();
registerHandlers(io, session);

httpServer.listen(PORT, () => {
  console.log(`[mock-server] listening on http://localhost:${PORT}`);
  console.log('[mock-server] connect the Vite UI (port 5173) — Simulate generates shots');
});
