import { useState } from 'react';
import { useLaunchDaddy } from './useLaunchDaddy';

interface Particle {
  id: number;
  tx: number;
  ty: number;
  type: string;
  delay: number;
  duration: number;
  startX: number;
  startY: number;
}

function generateParticles(count: number): Particle[] {
  return Array.from({ length: count }, (_, i) => {
    const angle = Math.random() * 360 * (Math.PI / 180);
    const distance = 100 + Math.random() * 400;
    return {
      id: i,
      tx: Math.cos(angle) * distance,
      ty: Math.sin(angle) * distance,
      type: ['fire', 'spark', 'ember'][Math.floor(Math.random() * 3)],
      delay: Math.random() * 0.3,
      duration: 0.8 + Math.random() * 0.7,
      startX: 45 + Math.random() * 10,
      startY: 55 + Math.random() * 10,
    };
  });
}

function randomFrom<T>(arr: readonly T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

const LAUNCH_PHRASES = [
  'STRATOSPHERE',
  'ORBIT ACHIEVED',
  'TO THE MOON',
  'NUCLEAR LAUNCH',
  'ABSOLUTE BOMB',
  'INTO ORBIT',
  'LAUNCHED',
  'OBLITERATED',
  'VAPORIZED',
] as const;

const SUBTITLES = [
  'THE LONGEST HITTER IN THE WORLD',
  'THAT BALL HAD A FAMILY',
  'CALL THE AUTHORITIES',
  'WEAPONS GRADE DISTANCE',
  'SPONSORED BY NASA',
  'REGISTERED AS A WEAPON',
  'BROKE THE SOUND BARRIER',
] as const;

interface ExplosionData {
  particles: Particle[];
  phrase: string;
  subtitle: string;
}

function generateExplosionData(): ExplosionData {
  return {
    particles: generateParticles(50),
    phrase: randomFrom(LAUNCH_PHRASES),
    subtitle: randomFrom(SUBTITLES),
  };
}

export function LaunchDaddyOverlay() {
  const { isExploding, isLaunchDaddyMode } = useLaunchDaddy();
  const [explosionData, setExplosionData] = useState<ExplosionData>(generateExplosionData);
  const [wasExploding, setWasExploding] = useState(false);

  // Regenerate random data when explosion starts
  if (isExploding && !wasExploding) {
    setExplosionData(generateExplosionData());
  }
  if (isExploding !== wasExploding) {
    setWasExploding(isExploding);
  }

  if (!isLaunchDaddyMode || !isExploding) return null;

  return (
    <>
      {/* Fire border effect */}
      <div className="launch-daddy-fire-border" />

      {/* Explosion flash and rings */}
      <div className="launch-daddy-explosion">
        <div className="launch-daddy-explosion__flash" />
        <div className="launch-daddy-explosion__ring" />
        <div className="launch-daddy-explosion__ring" />
        <div className="launch-daddy-explosion__ring" />

        {/* Particle system */}
        <div className="launch-daddy-explosion__particles">
          {explosionData.particles.map((particle) => (
            <div
              key={particle.id}
              className={`launch-daddy-particle launch-daddy-particle--${particle.type}`}
              style={
                {
                  left: `${particle.startX}%`,
                  top: `${particle.startY}%`,
                  '--tx': `${particle.tx}px`,
                  '--ty': `${particle.ty}px`,
                  animationDelay: `${particle.delay}s`,
                  animationDuration: `${particle.duration}s`,
                } as React.CSSProperties
              }
            />
          ))}
        </div>
      </div>

      {/* Stratosphere launch */}
      <div className="launch-daddy-stratosphere">
        <div className="launch-daddy-stratosphere__ball" />
        <div className="launch-daddy-stratosphere__text">{explosionData.phrase}</div>
        <div className="launch-daddy-stratosphere__subtitle">{explosionData.subtitle}</div>
      </div>
    </>
  );
}
