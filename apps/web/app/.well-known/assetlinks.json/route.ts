// Digital Asset Links for the Google Play app (a Trusted Web Activity of this site, see docs/app-stores.md): Android
// opens konsilier.com full screen inside the app only when this file names the app's package and signing key.
// ANDROID_CERT_SHA256 (comma-separated, "AB:CD:…") is set on the server once the signing key exists; until then the
// list is empty and nothing is claimed.
export const dynamic = "force-dynamic";

export function GET() {
  const pkg = process.env.ANDROID_PACKAGE || "com.konsilier.app";
  const fingerprints = (process.env.ANDROID_CERT_SHA256 ?? "").split(",").map((s) => s.trim().toUpperCase()).filter(Boolean);
  const body = fingerprints.length
    ? [{ relation: ["delegate_permission/common.handle_all_urls"],
        target: { namespace: "android_app", package_name: pkg, sha256_cert_fingerprints: fingerprints } }]
    : [];
  return Response.json(body, { headers: { "Cache-Control": "public, max-age=3600" } });
}
