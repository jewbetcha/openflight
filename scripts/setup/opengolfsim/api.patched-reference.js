import net from 'net';
import BaseLaunchMonitor from './base.js';
import { getGamePreferences } from '../store.js';
import { METERS_TO_MPH } from '../constants.js';

const defaults = {
  // host: '127.0.0.1',
  port: 3111
};

// [OpenFlight club-sync patch] Map an OGS club id (e.g. "7I", "3W", "DR") to an
// OpenConnect/GSPro club code ("I7", "W3", "DR"). OGS uses <number><letter>;
// OpenConnect uses <letter><number>. Driver/wedges/putter pass through.
function ogsClubToOpenConnect(clubId) {
  if (clubId === undefined || clubId === null) return 'DR';
  const id = String(clubId).trim().toUpperCase();
  if (['DR', 'PW', 'GW', 'SW', 'LW', 'PT'].includes(id)) return id;
  if (id === 'AW') return 'GW';
  const m = id.match(/^(\d)\s*([WHI])$/);
  if (m) return m[2] + m[1];
  return id;
}

export default class APILaunchMonitor extends BaseLaunchMonitor {
  constructor(config = {}) {
    super();
    this.config = { ...defaults, ...config };
    this.playSound = false;
    
    const gamePrefs = getGamePreferences();
    if (gamePrefs.launchMonitor.apiPort) {
      this.config.port = gamePrefs.launchMonitor.apiPort;
    }

    this.device = {
      isReady: false,
      isConnected: false
    };
    this.server = net.createServer(this._handleConnection.bind(this));
    this.connectedSockets = new Set();
    this.shotNumber = -1;
    // [OpenFlight club-sync patch] current club as an OpenConnect code.
    this.currentClub = 'DR';
  }

  // [OpenFlight club-sync patch] OGS calls setClub on every club change. Store
  // it (mapped to an OpenConnect code) and push a 201 Player to clients now.
  setClub(clubId) {
    super.setClub(clubId);
    this.currentClub = ogsClubToOpenConnect(clubId);
    const msg = JSON.stringify({
      Code: 201,
      Message: 'Player Information',
      Player: { Handed: 'RH', Club: this.currentClub }
    }) + '\n';
    for (const socket of this.connectedSockets) {
      try { socket.write(msg); } catch (e) { /* socket closing */ }
    }
  }

  _handleConnection(socket) {
    console.log(`Client connected from ${socket.remoteAddress}:${socket.remotePort}`);
    this.connectedSockets.add(socket);
    this.device.isConnected = true;
    this.emit('device', this.device);
    // Handle data received from the client
    socket.on('data', (data) => {
      // console.log(`Received data from client: ${data.toString()}`);
      // Echo the data back to the client
      try {
        const obj = JSON.parse(data.toString('utf-8'));
        if (obj.type === 'shot') {
          console.log('Received shot!', obj);
          if (obj.unit === 'metric') {
            // convert metric (m/s) ball speed to imperial (MPH)
            obj.shot.ballSpeed = obj.shot.ballSpeed * METERS_TO_MPH;
          }

          this.emit('shot', obj.shot);
        } else if (obj.type === 'device') {
          this.device.isReady = obj.status === 'ready';
          this.emit('device', this.device);

        } else if (!!obj.APIversion || !!obj.APIVersion || !!obj.BallData) {
          // GSPro API format, we should just handle it
          // if (obj.ShotNumber) {
          //   this.shotNumber = obj.ShotNumber;
          // }
          if (this.shotNumber < 0 && obj.ShotNumber) {
            this.shotNumber = obj.ShotNumber;
          }

          if (obj.BallData?.Speed > 0 && this.shotNumber < obj.ShotNumber) {
            this.shotNumber = obj.ShotNumber;
            const convertedShot = {
              ballSpeed: obj.BallData.Speed,
              spinAxis: obj.BallData.SpinAxis,
              spinSpeed: obj.BallData.TotalSpin,
              horizontalLaunchAngle: obj.BallData.HLA,
              verticalLaunchAngle: obj.BallData.VLA,
            };
            this.emit('shot', convertedShot);

            // reset shot / simulator ready event
            // needed for GSPro-based square LM integrations
            socket.__sentGSProReadyEvent = false;
            this.sendReadyEvent(socket);

            socket.write(JSON.stringify({
              "Code": 200,
              "Message": "Club Data received"
            }) + '\n');
            return;
          }

          if (obj.ShotDataOptions?.IsHeartBeat) {
            console.log('sending heart beat response');
            this.device.isReady = true;
            this.emit('device', this.device);

            socket.write(JSON.stringify({
              "Code": 200
            }) + '\n');

          } else {

            socket.write(JSON.stringify({
              "Code": 201,
              "Message": "Player Information",
              "Player": {
                "Handed": "RH",
                "Club": this.currentClub  // [OpenFlight club-sync patch] real club, not hardcoded "DR"
              }
            }) + '\n');
          }


          // early return here to avoid sending our standard response
          this.sendReadyEvent(socket);
          return;

        } else {
          console.log('Received other event', obj);
        }
        console.log('sending 200 response');
        socket.write(`${JSON.stringify({ status: 200 })}\n`);
      } catch (error) {
        console.log(error);
        socket.write(`${JSON.stringify({ status: 400, error: error.message })}\n`);
      }
    });

    // Handle client disconnection
    socket.on('end', () => {
      console.log('Client disconnected.');
      this.connectedSockets.delete(socket);
      this.device.isConnected = false;
      this.emit('device', this.device);
    });

    // Handle errors
    socket.on('error', (err) => {
      console.error(`Socket error: ${err.message}`);
      this.connectedSockets.delete(socket);
    });
  }

  sendReadyEvent(socket) {
    // needed for Square LM, not sure about others
    if (!socket.__sentGSProReadyEvent) {
      socket.__sentGSProReadyEvent = true;
      setTimeout(() => {
        socket.write(JSON.stringify({
          Code: 202,
          Message: 'GSPro ready',
          Player: null
        }) + '\n');
      }, 500);
    }
  }

  start() {
    this.server.on('close', () => {
      console.log('SERVER CLOSED');
    });
    this.server.listen(this.config.port, () => {
      console.log(`OGS API server listening on localhost:${this.config.port}`);
    });
  }

  stop() {
    return new Promise(resolve => {
      this.server.close();
      resolve();
    });
  }

  sendMessage(payload) {
    for (const socket of this.connectedSockets) {
      socket.write(JSON.stringify(payload) + "\n");
    }
  }
}