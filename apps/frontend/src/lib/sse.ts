/** Read a fetch SSE response. POST with credentials cannot use EventSource. */

export async function readEventStream(
  response: Response,
  onEvent: (event: string, data: Record<string, unknown>) => void,
): Promise<void> {
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error("The assistant did not return a stream.");
  }
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    buffer = drain(buffer, onEvent);
  }
  buffer += decoder.decode();
  drain(`${buffer}\n\n`, onEvent);
}

function drain(buffer: string, onEvent: (event: string, data: Record<string, unknown>) => void): string {
  const frames = buffer.split("\n\n");
  const rest = frames.pop() ?? "";
  for (const frame of frames) {
    if (!frame.trim()) {
      continue;
    }
    let event = "message";
    const dataLines: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) {
        event = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trim());
      }
    }
    if (dataLines.length === 0) {
      continue;
    }
    onEvent(event, JSON.parse(dataLines.join("\n")) as Record<string, unknown>);
  }
  return rest;
}
