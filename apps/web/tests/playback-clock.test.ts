import assert from 'node:assert/strict'
import { test } from 'node:test'
import { PlaybackClock } from '../src/lib/playback-clock.ts'

test('pause, seek and speed preserve one time independent of sampling cadence', () => {
  const clock = new PlaybackClock(100)
  clock.play(1000)
  assert.equal(clock.sample(3500).seconds, 2.5)
  clock.setSpeed(4, 3500)
  assert.equal(clock.sample(4000).seconds, 4.5)
  clock.pause(4000)
  assert.deepEqual(clock.sample(9000), { seconds: 4.5, playing: false })
  clock.seek(30.123, 9000)
  clock.play(10000)
  assert.ok(Math.abs(clock.sample(11000).seconds - 34.123) < 1e-9)
})

test('clock clamps boundaries and stops at the end', () => {
  const clock = new PlaybackClock(10)
  clock.seek(-1, 0)
  assert.equal(clock.sample(0).seconds, 0)
  clock.seek(9, 0)
  clock.play(0)
  assert.deepEqual(clock.sample(2000), { seconds: 10, playing: false })
  clock.seek(5, 2000)
  assert.deepEqual(clock.sample(3000), { seconds: 5, playing: false })
  clock.seek(10, 3000)
  clock.play(4000)
  assert.deepEqual(clock.sample(4000), { seconds: 0, playing: true })
  assert.throws(() => clock.seek(Number.NaN, 0))
  assert.throws(() => clock.setSpeed(0, 0))
})
