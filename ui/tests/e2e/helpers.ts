import { expect, type Page } from '@playwright/test';
import { io, type Socket } from 'socket.io-client';

const UI_URL = 'http://127.0.0.1:5173';
const SOCKET_URL = 'http://127.0.0.1:8080';

function connectSocket(): Promise<Socket> {
  return new Promise((resolve, reject) => {
    const socket = io(SOCKET_URL, {
      transports: ['websocket', 'polling'],
    });

    const onConnect = () => {
      socket.off('connect_error', onError);
      resolve(socket);
    };

    const onError = (error: Error) => {
      socket.off('connect', onConnect);
      socket.close();
      reject(error);
    };

    socket.once('connect', onConnect);
    socket.once('connect_error', onError);
  });
}

export async function withControlSocket<T>(run: (socket: Socket) => Promise<T>): Promise<T> {
  const socket = await connectSocket();

  try {
    return await run(socket);
  } finally {
    socket.close();
  }
}

export async function setClub(socket: Socket, club: string) {
  socket.emit('set_club', { club });
  await waitForEvent(socket, 'club_changed');
}

export async function simulateShot(socket: Socket) {
  socket.emit('simulate_shot');
  return waitForEvent(socket, 'shot');
}

export async function waitForEvent<T>(socket: Socket, event: string, timeoutMs = 5000): Promise<T> {
  return new Promise((resolve, reject) => {
    const timeout = setTimeout(() => {
      socket.off(event, onEvent);
      reject(new Error(`Timed out waiting for ${event}`));
    }, timeoutMs);

    const onEvent = (payload: T) => {
      clearTimeout(timeout);
      socket.off(event, onEvent);
      resolve(payload);
    };

    socket.on(event, onEvent);
  });
}

export async function gotoApp(page: Page, path = '/') {
  await page.goto(`${UI_URL}${path}`);
}

export { expect };
