// Files shared to the app are normally caught by the service worker (public/sw.js) before they reach the server.
// Without it (the very first launch, a cleared browser), the request lands here: /share asks to share again.
export function POST() {
  return new Response(null, { status: 303, headers: { Location: "/share?error=1" } });
}
