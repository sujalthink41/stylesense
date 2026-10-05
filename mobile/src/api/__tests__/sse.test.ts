import { SSEParser } from '../sse';

describe('SSE parser', () => {
  it('reads named events with ids', () => {
    const p = new SSEParser();

    expect(p.feed('id: 3.1\nevent: ui.loading\ndata: {"a":1}\n\n')).toEqual([{ id: '3.1', event: 'ui.loading', data: '{"a":1}' }]);
  });

  it('joins frames split across network chunks, even mid-line', () => {
    const p = new SSEParser();

    expect(p.feed('event: ui.ren')).toEqual([]);
    expect(p.feed('der\ndata: {"x"')).toEqual([]);
    expect(p.feed(':1}\n')).toEqual([]);
    expect(p.feed('\nevent: done\ndata: {}\n\n')).toEqual([
      { event: 'ui.render', data: '{"x":1}' },
      { event: 'done', data: '{}' },
    ]);
  });

  it('ignores keep-alive comments and accepts CRLF line ends', () => {
    const p = new SSEParser();

    expect(p.feed(': keep-alive\n\n: keep-alive\r\n\r\nevent: done\r\ndata: {}\r\n\r\n')).toEqual([{ event: 'done', data: '{}' }]);
  });

  it('joins multi-line data and defaults the event name', () => {
    const p = new SSEParser();

    expect(p.feed('data: one\ndata:two\n\n')).toEqual([{ event: 'message', data: 'one\ntwo' }]);
  });

  it('drops frames without data and reports a trailing frame only once complete', () => {
    const p = new SSEParser();

    expect(p.feed('event: lonely\n\nevent: half\ndata: x')).toEqual([]);
    expect(p.flush()).toEqual([{ event: 'half', data: 'x' }]);
    expect(p.flush()).toEqual([]);
  });
});
