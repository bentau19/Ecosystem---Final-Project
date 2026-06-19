package com.example.android.domain.usecases;

import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.Paint;
import android.util.Log;

import com.example.android.enums.WebcamChannels;
import com.example.android.network.transport.TransportManager;
import com.example.android.repositories.WebcamRepository;

import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.IOException;
import java.io.PipedInputStream;
import java.io.PipedOutputStream;

/**
 * Streams JPEG frames from Android to the PC over the webcam channel.
 *
 * Phase 1 (PoC): sends a static solid-color frame in a loop instead of live camera.
 *
 * Protocol (Android → PC):
 *   1. Send handshake JSON on WEBCAM_START so the PC opens OBS Virtual Camera.
 *   2. Open WEBCAM_FRAMES and stream frames continuously:
 *      [4-byte big-endian frame size][JPEG bytes]  (repeated until stop())
 *
 * Threading model:
 *   execute() blocks on a background thread (called by ConnectivityService).
 *   A PipedInputStream/PipedOutputStream pair keeps the channel open for the
 *   full session — writing stops when stop() closes the pipe.
 */
public class WebcamStreamUseCase {

    private static final String TAG = "WebcamStreamUseCase";

    private static final int WIDTH  = 640;
    private static final int HEIGHT = 480;
    private static final int FPS    = 15;
    private static final long FRAME_INTERVAL_MS = 1000L / FPS;

    private final TransportManager transport;
    private final WebcamRepository  repository;

    private volatile boolean stopRequested = false;
    private volatile PipedOutputStream pipedOut;

    public WebcamStreamUseCase(TransportManager transport, WebcamRepository repository) {
        this.transport  = transport;
        this.repository = repository;
    }

    /** Signal the streaming loop to stop and close the channel. */
    public void stop() {
        stopRequested = true;
        try {
            if (pipedOut != null) pipedOut.close();
        } catch (Exception ignored) {}
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

            // 2. Pipe: streaming thread writes frames; streamInputStreamToChannel reads them.
            PipedInputStream  pipedIn  = new PipedInputStream(131072); // 128 KB — must fit one full JPEG frame
            pipedOut = new PipedOutputStream(pipedIn);
            DataOutputStream  dos      = new DataOutputStream(pipedOut);

            // Producer thread: draws a dynamic frame (counter + alternating colors) per tick.
            // Proves latency and FPS are real — a frozen counter means a clogged pipeline.
            Thread producer = new Thread(() -> {
                Paint textPaint = new Paint();
                textPaint.setColor(Color.WHITE);
                textPaint.setTextSize(50f);
                int frameCount = 0;
                try {
                    while (!stopRequested) {
                        Bitmap bmp = Bitmap.createBitmap(WIDTH, HEIGHT, Bitmap.Config.ARGB_8888);
                        Canvas canvas = new Canvas(bmp);
                        canvas.drawColor(frameCount % 2 == 0 ? Color.BLUE : Color.RED);
                        canvas.drawText("Frame: " + frameCount, 50, 240, textPaint);

                        ByteArrayOutputStream baos = new ByteArrayOutputStream();
                        bmp.compress(Bitmap.CompressFormat.JPEG, 50, baos);
                        bmp.recycle();
                        byte[] frame = baos.toByteArray();

                        try {
                            dos.writeInt(frame.length);
                            dos.write(frame);
                            dos.flush();
                        } catch (IOException e) {
                            if (!stopRequested) Log.w(TAG, "Pipe broken — network dropped during stream");
                            break;
                        }

                        frameCount++;
                        Thread.sleep(FRAME_INTERVAL_MS);
                    }
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                } catch (Exception e) {
                    if (!stopRequested) Log.e(TAG, "Frame producer error", e);
                } finally {
                    try { pipedOut.close(); } catch (Exception ignored) {}
                }
            }, "webcam-producer");
            producer.setDaemon(true);
            producer.start();

            // Consumer: blocks until the pipe closes (stop() or producer error).
            transport.streamInputStreamToChannel(WebcamChannels.WEBCAM_FRAMES.getValue(), pipedIn);

            producer.join(2000);
            repository.onStreamStopped();

        } catch (Exception e) {
            Log.e(TAG, "Webcam stream error", e);
            repository.onStreamFailed();
        }
    }

}
