package com.example.android.domain.usecases;

import android.util.Log;

import com.example.android.enums.WebcamChannels;
import com.example.android.network.transport.TransportManager;
import com.example.android.repositories.WebcamRepository;

import java.nio.ByteBuffer;
import java.util.concurrent.TimeUnit;

/**
 * Streams JPEG frames from Android to the PC over the webcam channel.
 *
 * Protocol (Android → PC):
 *   1. Send handshake JSON on WEBCAM_START so the PC opens OBS Virtual Camera.
 *   2. Open WEBCAM_FRAMES and stream frames continuously:
 *      [4-byte big-endian frame size][JPEG bytes]  (repeated until stop())
 *
 * Latency model:
 *   Every stage of this path prefers a fresh frame over a complete history — CameraX keeps only
 *   the latest, the repository queue drops the oldest when full, and each frame is written the
 *   moment it is pulled. Nothing here waits for a second frame before sending the first: in a live
 *   stream a buffered frame is simply a late one.
 *
 * Threading model:
 *   execute() blocks on a background thread (called by ConnectivityService) for the whole
 *   session, pulling frames until stop() is called.
 */
public class WebcamStreamUseCase {

    private static final String TAG = "WebcamStreamUseCase";

    /** How long a frame pull waits before looping to re-check {@link #stopRequested}. */
    private static final long FRAME_POLL_TIMEOUT_MS = 200;

    /** Big-endian frame length that prefixes every JPEG on the wire. */
    private static final int FRAME_HEADER_BYTES = 4;

    private final TransportManager transport;
    private final WebcamRepository  repository;

    private volatile boolean stopRequested = false;

    public WebcamStreamUseCase(TransportManager transport, WebcamRepository repository) {
        this.transport  = transport;
        this.repository = repository;
    }

    /** Signal the streaming loop to stop and close the channel. */
    public void stop() {
        stopRequested = true;
    }

    /**
     * Starts the handshake and then streams frames until stop() is called.
     * Must be called on a background thread — all I/O is synchronous.
     */
    public void execute() {
        stopRequested = false;
        try {
            // 1. Handshake: tell the PC to open OBS Virtual Camera.
            transport.writeToChannel(WebcamChannels.WEBCAM_START.getValue(), "{\"action\":\"start\"}");
            Log.d(TAG, "Handshake sent on " + WebcamChannels.WEBCAM_START.getValue());

            // 2. Frames, until stop() is requested or the channel breaks.
            transport.streamFramesToChannel(WebcamChannels.WEBCAM_FRAMES.getValue(), this::nextFrame);

            repository.onStreamStopped();

        } catch (Exception e) {
            Log.e(TAG, "Webcam stream error", e);
            repository.onStreamFailed();
        }
    }

    /**
     * Waits for the next camera frame and returns it length-prefixed, ready for the wire, or
     * {@code null} once streaming has been stopped. Polls with a timeout so a stop is noticed
     * promptly even while the camera is producing nothing.
     */
    private byte[] nextFrame() throws InterruptedException {
        while (!stopRequested) {
            byte[] jpeg = repository.frameQueue.poll(FRAME_POLL_TIMEOUT_MS, TimeUnit.MILLISECONDS);
            if (jpeg != null) {
                return withLengthPrefix(jpeg);
            }
        }
        return null;
    }

    /**
     * Header and payload are joined into one buffer so a frame reaches the wire as a single write.
     * Two writes would be two independent routing decisions, which could put a frame's header and
     * its body on different links.
     */
    private static byte[] withLengthPrefix(byte[] jpeg) {
        return ByteBuffer.allocate(FRAME_HEADER_BYTES + jpeg.length)
                .putInt(jpeg.length)
                .put(jpeg)
                .array();
    }
}
