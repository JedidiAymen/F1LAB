/** One monotonic playback clock; render/poll cadence never defines race time. */
export class PlaybackClock {
  private anchorSeconds = 0
  private anchorMilliseconds = 0
  private running = false
  private rate = 1
  readonly duration: number

  constructor(duration: number) {
    if (!Number.isFinite(duration) || duration < 0)
      throw new Error('Invalid replay duration')
    this.duration = duration
  }

  sample(now: number) {
    const seconds = Math.min(
      this.duration,
      this.anchorSeconds +
        (this.running
          ? (Math.max(0, now - this.anchorMilliseconds) / 1000) * this.rate
          : 0),
    )
    return { seconds, playing: this.running && seconds < this.duration }
  }

  play(now: number) {
    const { seconds } = this.sample(now)
    this.anchorSeconds = seconds >= this.duration ? 0 : seconds
    this.anchorMilliseconds = now
    this.running = this.duration > 0
  }

  pause(now: number) {
    this.anchorSeconds = this.sample(now).seconds
    this.anchorMilliseconds = now
    this.running = false
  }

  seek(seconds: number, now: number) {
    if (!Number.isFinite(seconds)) throw new Error('Invalid seek time')
    const wasPlaying = this.sample(now).playing
    this.anchorSeconds = Math.max(0, Math.min(this.duration, seconds))
    this.anchorMilliseconds = now
    this.running = wasPlaying && this.anchorSeconds < this.duration
  }

  setSpeed(speed: number, now: number) {
    if (!Number.isFinite(speed) || speed <= 0 || speed > 16)
      throw new Error('Invalid playback speed')
    const state = this.sample(now)
    this.anchorSeconds = state.seconds
    this.running = state.playing
    this.anchorMilliseconds = now
    this.rate = speed
  }
}
