package com.example.android.viewmodel;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.MutableLiveData;
import androidx.lifecycle.ViewModel;

import com.example.android.domain.enums.WebcamStatus;
import com.example.android.repositories.SettingsRepository;
import com.example.android.repositories.WebcamRepository;

/**
 * ViewModel responsible for the webcam streaming feature (Android → PC).
 *
 * Responsibilities:
 * - Exposes LiveData for the UI to observe streaming state
 * - Delegates user actions (start / stop / reset) to the Repository
 *
 * What it does NOT do:
 * - Does not touch the network (that's WebcamStreamUseCase's job)
 * - Does not know about TauSync, channels, or camera APIs
 * - Does not hold a Context reference
 *
 * Scoped to MainActivity so the streaming state survives fragment transitions.
 */
public class WebcamViewModel extends ViewModel {

    private final WebcamRepository   repository         = WebcamRepository.getInstance();

    /**
     * Emits {@code true} once when the user taps Start but webcam is disabled in Settings.
     * The Fragment observes this to show a Snackbar/Toast and stay on the Start screen.
     */
    private final MutableLiveData<Boolean> webcamDisabledEvent = new MutableLiveData<>();

    // ── Observers ──────────────────────────────────────────────────────────────

    /** @return LiveData with the current webcam session status. */
    public LiveData<WebcamStatus> getStatus() {
        return repository.getStatus();
    }

    /**
     * One-shot event fired when the user tries to start the webcam but it is disabled
     * in Settings. The Fragment should observe this and show an error message.
     */
    public LiveData<Boolean> getWebcamDisabledEvent() {
        return webcamDisabledEvent;
    }

    // ── User actions ───────────────────────────────────────────────────────────

    /**
     * Called when the user taps Start.
     * If webcam is disabled in Settings, fires {@link #getWebcamDisabledEvent()} instead
     * of starting the stream so the Fragment can surface a helpful error.
     */
    public void startStream() {
        if (!SettingsRepository.getInstance().isWebcamEnabled()) {
            webcamDisabledEvent.setValue(true);
            return;
        }
        repository.requestStart();
    }

    /** Called when the user taps Stop — signals the use case to close the channel. */
    public void stopStream() {
        repository.requestStop();
    }

    /** Resets to IDLE after the UI has acknowledged a terminal state. */
    public void reset() {
        repository.reset();
    }

    /** Clears the one-shot disabled event after the Fragment has handled it. */
    public void clearWebcamDisabledEvent() {
        webcamDisabledEvent.setValue(null);
    }
}
