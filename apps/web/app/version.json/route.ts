// The id of the build the server runs now (the same value is baked into the pages): an open tab compares it with its
// own and reloads when they differ (components/VersionWatch.tsx).
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ id: process.env.NEXT_PUBLIC_BUILD_ID ?? null },
    { headers: { "Cache-Control": "no-store, max-age=0" } });
}
