import { create } from 'zustand';

const PLAYERS_STORAGE_KEY = 'openflight-players';
const SELECTED_PLAYER_STORAGE_KEY = 'openflight-selected-player';
const DEFAULT_PLAYER = 'Player 1';

function cleanPlayerName(name: string): string {
  return name.trim().slice(0, 40);
}

function loadPlayers(): string[] {
  if (typeof window === 'undefined') return [DEFAULT_PLAYER];

  try {
    const raw = window.localStorage.getItem(PLAYERS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : null;
    if (Array.isArray(parsed)) {
      const players = parsed.map((name) => cleanPlayerName(String(name))).filter(Boolean);
      return Array.from(new Set(players)).slice(0, 12);
    }
  } catch {
    // Ignore broken localStorage data and fall back to the default.
  }
  return [DEFAULT_PLAYER];
}

function savePlayers(players: string[]) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(PLAYERS_STORAGE_KEY, JSON.stringify(players));
  } catch {
    // Ignore storage failures; the picker still works for the current session.
  }
}

function saveSelectedPlayer(playerName: string) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(SELECTED_PLAYER_STORAGE_KEY, playerName);
  } catch {
    // Ignore storage failures; the picker still works for the current session.
  }
}

function loadSelectedPlayer(): string {
  if (typeof window === 'undefined') return '';
  try {
    return cleanPlayerName(window.localStorage.getItem(SELECTED_PLAYER_STORAGE_KEY) ?? '');
  } catch {
    return '';
  }
}

interface PlayerState {
  players: string[];
  selectedPlayer: string;
  addPlayer: (name: string) => string;
  removePlayer: (name: string) => void;
  selectPlayer: (name: string) => void;
}

const initialPlayers = loadPlayers();
const savedSelected = loadSelectedPlayer();
const initialSelected = initialPlayers.includes(savedSelected) ? savedSelected : (initialPlayers[0] ?? DEFAULT_PLAYER);

export const usePlayerStore = create<PlayerState>((set, get) => ({
  players: initialPlayers.length ? initialPlayers : [DEFAULT_PLAYER],
  selectedPlayer: initialSelected,
  addPlayer: (name) => {
    const playerName = cleanPlayerName(name) || DEFAULT_PLAYER;
    const nextPlayers = Array.from(new Set([...get().players, playerName])).slice(0, 12);
    savePlayers(nextPlayers);
    saveSelectedPlayer(playerName);
    set({ players: nextPlayers, selectedPlayer: playerName });
    return playerName;
  },
  removePlayer: (name) => {
    const current = get();
    if (current.selectedPlayer === name) return;
    const remaining = current.players.filter((player) => player !== name);
    const nextPlayers = remaining.length ? remaining : [DEFAULT_PLAYER];
    savePlayers(nextPlayers);
    saveSelectedPlayer(current.selectedPlayer);
    set({ players: nextPlayers, selectedPlayer: current.selectedPlayer });
  },
  selectPlayer: (name) => {
    const playerName = cleanPlayerName(name) || DEFAULT_PLAYER;
    const nextPlayers = get().players.includes(playerName)
      ? get().players
      : [...get().players, playerName].slice(0, 12);
    savePlayers(nextPlayers);
    saveSelectedPlayer(playerName);
    set({ players: nextPlayers, selectedPlayer: playerName });
  },
}));
