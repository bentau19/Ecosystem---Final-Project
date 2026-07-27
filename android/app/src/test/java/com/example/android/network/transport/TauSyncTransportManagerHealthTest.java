package com.example.android.network.transport;

import static org.junit.Assert.assertEquals;

import com.example.android.network.transport.TauSyncTransportManager.Health;

import org.junit.Test;

/**
 * Unit tests for the poll-loop connection-health watchdog
 * ({@link TauSyncTransportManager#evaluateHealth(long[], boolean, long, long)}).
 *
 * <p>The method is static and pure (its only state is the caller-owned {@code lostSince} marker),
 * so these run as plain JVM tests with no Android framework / Robolectric. Timestamps use a
 * non-zero base because 0 is the marker's "healthy" sentinel (a real currentTimeMillis() is never 0).
 */
public class TauSyncTransportManagerHealthTest {

    private static final long GRACE = 10_000L;
    private static final long T0 = 1_000_000L; // arbitrary non-zero epoch-ms base

    @Test
    public void connected_isHealthy_andClearsMarker() {
        long[] lostSince = {0L};

        // A down tick arms the marker...
        assertEquals(Health.WITHIN_GRACE, TauSyncTransportManager.evaluateHealth(lostSince, false, T0, GRACE));
        assertEquals(T0, lostSince[0]);

        // ...a healthy tick clears it.
        assertEquals(Health.HEALTHY, TauSyncTransportManager.evaluateHealth(lostSince, true, T0 + 1, GRACE));
        assertEquals(0L, lostSince[0]);
    }

    @Test
    public void firstDownTick_isWithinGrace() {
        long[] lostSince = {0L};
        assertEquals(Health.WITHIN_GRACE, TauSyncTransportManager.evaluateHealth(lostSince, false, T0, GRACE));
    }

    @Test
    public void downBeforeGraceElapses_staysWithinGrace() {
        long[] lostSince = {0L};
        TauSyncTransportManager.evaluateHealth(lostSince, false, T0, GRACE);                  // arm
        assertEquals(Health.WITHIN_GRACE,
                TauSyncTransportManager.evaluateHealth(lostSince, false, T0 + GRACE - 1, GRACE));
    }

    @Test
    public void downAtGraceBoundary_isLost() {
        long[] lostSince = {0L};
        TauSyncTransportManager.evaluateHealth(lostSince, false, T0, GRACE);                  // arm
        assertEquals(Health.LOST,
                TauSyncTransportManager.evaluateHealth(lostSince, false, T0 + GRACE, GRACE));
    }

    @Test
    public void recoveryMidGrace_restartsWindow_neverLost() {
        long[] lostSince = {0L};
        TauSyncTransportManager.evaluateHealth(lostSince, false, T0, GRACE);                  // arm at T0
        assertEquals(Health.HEALTHY,
                TauSyncTransportManager.evaluateHealth(lostSince, true, T0 + 5_000L, GRACE)); // recovered

        // A new down streak starts a fresh window from its own first tick, so a point that would
        // have been LOST relative to the original arm is still only WITHIN_GRACE.
        TauSyncTransportManager.evaluateHealth(lostSince, false, T0 + 6_000L, GRACE);         // re-arm
        assertEquals(Health.WITHIN_GRACE,
                TauSyncTransportManager.evaluateHealth(lostSince, false, T0 + 15_000L, GRACE)); // 9s into new window
    }
}
