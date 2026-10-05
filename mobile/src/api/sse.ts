export interface SSEEvent {
  event: string;
  data: string;
  id?: string;
}

/**
 * Incremental Server-Sent Events parser: feed it chunks as they arrive, get whole events back.
 * Chunks may split anywhere, including inside a line.
 */
export class SSEParser {
  private buffer = '';
  private frame: { event?: string; data: string[]; id?: string } = { data: [] };

  feed(chunk: string): SSEEvent[] {
    this.buffer += chunk;
    const out: SSEEvent[] = [];
    let nl: number;
    while ((nl = this.buffer.indexOf('\n')) >= 0) {
      const line = this.buffer.slice(0, nl).replace(/\r$/, '');
      this.buffer = this.buffer.slice(nl + 1);
      if (line === '') {
        const event = this.take();
        if (event) out.push(event);
      } else {
        this.field(line);
      }
    }
    return out;
  }

  /** End of stream: a last frame without its blank line still counts. */
  flush(): SSEEvent[] {
    if (this.buffer) {
      this.field(this.buffer.replace(/\r$/, ''));
      this.buffer = '';
    }
    const event = this.take();
    return event ? [event] : [];
  }

  private field(line: string) {
    if (line.startsWith(':')) return; // comment (keep-alive)
    const colon = line.indexOf(':');
    const name = colon < 0 ? line : line.slice(0, colon);
    const value = colon < 0 ? '' : line.slice(colon + 1).replace(/^ /, '');
    if (name === 'data') this.frame.data.push(value);
    else if (name === 'event') this.frame.event = value;
    else if (name === 'id') this.frame.id = value;
  }

  private take(): SSEEvent | null {
    const { event, data, id } = this.frame;
    this.frame = { data: [] };
    if (!data.length) return null;
    return { event: event ?? 'message', data: data.join('\n'), ...(id !== undefined ? { id } : {}) };
  }
}
