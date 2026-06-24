package com.example.android.repositories;

import android.util.Log;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;

import com.example.android.domain.enums.WebcamStatus;

import java.util.concurrent.LinkedBlockingQueue;

/**
 * Repository responsible for webcam streaming state (Android → PC).
 *
 * Single Responsibility: tracks the lifecycle of one webcam session at a time.
 * Mirrors SendFileRepository — same singleton + LiveData + listener pattern.
 *
 * Lifecycle:
 *   IDLE → STREAMING  (user taps Start)
 *   STREAMING → STOPPED (user taps Stop or stream ends gracefully)
 *   (any state) → FAILED (network / I/O error)
 */
public class WebcamRepository {

    private static WebcamRepository instance;
    private static final String TAG = "WebcamRepository";

    private final MutableLiveData<WebcamStatus> status =
            new MutableLiveData<>(WebcamStatus.IDLE);

    /**
     * Bridge between WebcamFragment (CameraX producer) and WebcamStreamUseCase (consumer).
     * Capacity=2: if the network is slower than the camera, old frames are dropped rather
     * than buffering indefinitely and causing an OOM crash.
     */
    public final LinkedBlockingQueue<byte[]> frameQueue = new LinkedBlockingQueue<>(2);

    /** Implemented by ConnectivityService — runs actual network I/O on a background thread. */
    public interface StreamActionListener {
        void onStartRequested();
        void onStopRequested();
    }

    private StreamActionListener actionListener;

    private WebcamRepository() {}

    public static synchronized WebcamRepository getInstance() {
        if (instance == null) {
            instance = new WebcamRepository();
        }
        return instance;
    }

    public void setActionListener(StreamActionListener listener) {
        this.actionListener = listener;
    }

    // ── Observers ──────────────────────────────────────────────────────────────

    public LiveData<WebcamStatus> getStatus() {
        return status;
    }

    // ── User actions (called by ViewModel) ────────────────────────────────────

    public void requestStart() {
        Log.d(TAG, "Webcam start requested");
        status.postValue(WebcamStatus.STREAMING);
        if (actionListener != null) {
            actionListener.onStartRequested();
        } else {
            Log.w(TAG, "No StreamActionListener registered — is ConnectivityService running?");
            status.postValue(WebcamStatus.FAILED);
        }
    }

    public void requestStop() {
        Log.d(TAG, "Webcam stop requested");
        if (actionListener != null) {
            actionListener.onStopRequested();
        }
    }

    // ── State transitions (called by WebcamStreamUseCase) ─────────────────────

    public void onStreamStopped() {
        Log.d(TAG, "Webcam stream stopped");
        status.postValue(WebcamStatus.STOPPED);
    }

    public void onStreamFailed() {
        Log.e(TAG, "Webcam stream failed");
        status.postValue(WebcamStatus.FAILED);
    }

    public void reset() {
        frameQueue.clear();
        status.postValue(WebcamStatus.IDLE);
    }
}
