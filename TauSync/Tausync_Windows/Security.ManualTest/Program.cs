using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using TauSync.Core;
using TauSync.Implementations.Management;
using TauSync.Implementations.Protocol;
using TauSync.Implementations.Security;
using TauSync.Models;

// Security-layer in-process tests (no hardware, single ConnectionContext).
//
// Covers:
//   1. ECDH key agreement: two SecuritySession instances derive the same key (cross-encrypt/decrypt).
//   2. Gating: encrypt/decrypt are pass-throughs until a key is derived, and for empty payloads.
//   3. Full pipeline through the singleton: BuildFrame encrypts the payload, the TPack header
//      (TargetID/Flags) stays plaintext so routing never decrypts, and Dispatch decrypts before the
//      handler — the handler receives the original plaintext.
//   4. Routing without decryption: a frame to an unknown TargetID is dropped (no decrypt, no throw).

int failures = 0;
void Pass(string label, string detail) => Console.WriteLine($"  PASS {label}: {detail}");
void Fail(string label, string detail) { Console.WriteLine($"  FAIL {label}: {detail}"); failures++; }

// ── Test 1: two sessions derive the same key ───────────────────────────
{
    var a = new SecuritySession();
    var b = new SecuritySession();
    string pubA = a.GenerateLocalPublicKey();
    string pubB = b.GenerateLocalPublicKey();
    a.CompleteExchange(pubB);
    b.CompleteExchange(pubA);

    if (a.IsEncryptionActive && b.IsEncryptionActive) Pass("ke-active", "both sessions active after exchange");
    else Fail("ke-active", "a or b not active");

    byte[] plain = Encoding.UTF8.GetBytes("the meeting word is CLIPBOARD");
    byte[] cipher = a.EncryptPayload(plain);
    byte[] round = b.DecryptPayload(cipher);
    if (round.SequenceEqual(plain)) Pass("ke-agree", "B decrypted what A encrypted (same derived key)");
    else Fail("ke-agree", "cross-decrypt mismatch — keys differ");

    if (!cipher.SequenceEqual(plain) && cipher.Length == plain.Length + 12 + 16)
        Pass("ke-overhead", $"ciphertext is IV+ct+tag ({cipher.Length} = {plain.Length}+28)");
    else
        Fail("ke-overhead", $"unexpected ciphertext length {cipher.Length}");
}

// ── Test 2: gating (inactive pass-through, empty pass-through) ──────────
{
    var s = new SecuritySession();
    byte[] data = { 1, 2, 3, 4 };
    if (ReferenceEquals(s.EncryptPayload(data), data)) Pass("gate-inactive", "no encryption before key exchange");
    else Fail("gate-inactive", "encrypted while inactive");

    s.GenerateLocalPublicKey();
    var peer = new SecuritySession();
    s.CompleteExchange(peer.GenerateLocalPublicKey());
    byte[] empty = Array.Empty<byte>();
    if (s.EncryptPayload(empty).Length == 0) Pass("gate-empty", "empty payload stays empty (FIN/barrier)");
    else Fail("gate-empty", "empty payload was expanded");
}

// ── Test 3: full pipeline through the singleton ────────────────────────
{
    var ctx = ConnectionContext.Instance;
    var protocol = new ProtocolHandler();
    ctx.Reset();
    ctx.BeginKeyExchange();

    // Drive the singleton's key exchange by feeding it a peer KEY_EXCHANGE frame (as the receive loop
    // would), so the singleton derives a key against its own freshly generated key pair.
    var peer = new SecuritySession();
    string peerPub = peer.GenerateLocalPublicKey();
    var keMsg = new KeyExchangeMessage
    {
        MagicBytes = CoreConfig.MagicBytes, Type = KeyExchangeMessage.TypeKeyExchange, PublicKey = peerPub
    };
    byte[] keBody = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(keMsg));
    ctx.Dispatch(CoreConfig.ControlChannelId, keBody, CoreConfig.FlagControl);

    if (ctx.IsEncryptionActive) Pass("singleton-ke", "KEY_EXCHANGE frame activated encryption synchronously");
    else Fail("singleton-ke", "encryption not active after KEY_EXCHANGE dispatch");

    // Build a data frame: BuildFrame encrypts the payload, header stays plaintext.
    const int targetId = 7;
    byte[] plaintext = Encoding.UTF8.GetBytes("hello over the encrypted channel");
    byte[] frame = protocol.BuildFrame(targetId, plaintext, 0);
    (int parsedTarget, byte[] wirePayload, byte parsedFlags) = protocol.ParseFrame(frame);

    if (parsedTarget == targetId && parsedFlags == 0)
        Pass("header-plaintext", "TargetID/Flags readable from the header without decrypting");
    else
        Fail("header-plaintext", $"header mismatch: target={parsedTarget} flags={parsedFlags}");

    if (!wirePayload.SequenceEqual(plaintext) && wirePayload.Length == plaintext.Length + 28)
        Pass("wire-encrypted", "on-wire payload is ciphertext, not plaintext");
    else
        Fail("wire-encrypted", $"payload not encrypted (len {wirePayload.Length})");

    // Register a handler and dispatch the parsed (ciphertext) payload — Dispatch must decrypt.
    byte[]? delivered = null;
    ctx.RegisterHandler(targetId, (payload, flags) => delivered = payload);
    ctx.SetTargetForSend(targetId, 99);
    ctx.Dispatch(targetId, wirePayload, 0);

    if (delivered != null && delivered.SequenceEqual(plaintext))
        Pass("roundtrip", "handler received the original plaintext after Dispatch decrypt");
    else
        Fail("roundtrip", "handler did not receive the original plaintext");

    // ── Test 4: unknown TargetID is dropped without decrypting (no throw) ──
    bool handled;
    try
    {
        handled = ctx.Dispatch(123456, wirePayload, 0); // no handler registered
        if (!handled) Pass("route-drop", "unknown TargetID dropped without decryption/throw");
        else Fail("route-drop", "unexpectedly handled unknown TargetID");
    }
    catch (Exception ex)
    {
        Fail("route-drop", $"threw instead of dropping: {ex.GetType().Name}");
    }

    ctx.Reset();
    if (!ctx.IsEncryptionActive) Pass("reset-clears", "Reset() deactivated encryption");
    else Fail("reset-clears", "encryption still active after Reset()");
}

// ── Test 5: cross-platform key-derivation parity (no JVM needed) ────────
// The C# side derives the AES key with DeriveKeyFromHash(SHA256); the Java side computes
// SHA-256(generateSecret()), where generateSecret() is the raw P-256 X coordinate. Prove the two are
// byte-identical so a key derived on Windows matches one derived on Android.
{
    using var e1 = ECDiffieHellman.Create(ECCurve.NamedCurves.nistP256);
    using var e2 = ECDiffieHellman.Create(ECCurve.NamedCurves.nistP256);
    byte[] viaHash = e1.DeriveKeyFromHash(e2.PublicKey, HashAlgorithmName.SHA256);     // C# SecuritySession
    byte[] rawX = e1.DeriveRawSecretAgreement(e2.PublicKey);                            // == Java generateSecret()
    byte[] viaManual = SHA256.HashData(rawX);                                           // Java SecuritySession
    if (viaHash.SequenceEqual(viaManual) && viaHash.Length == 32)
        Pass("interop-derivation", "DeriveKeyFromHash(SHA256) == SHA256(raw X coord) — matches Java");
    else
        Fail("interop-derivation", "C# and Java would derive different keys");
}

Console.WriteLine();
Console.WriteLine(failures == 0 ? "ALL CHECKS PASSED" : $"{failures} CHECK(S) FAILED");
return failures == 0 ? 0 : 1;
