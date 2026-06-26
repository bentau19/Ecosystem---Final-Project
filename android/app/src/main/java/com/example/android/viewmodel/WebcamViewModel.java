package com.example.android.viewmodel;

import androidx.lifecycle.LiveData;
import androidx.lifecycle.ViewModel;

import com.example.android.domain.enums.WebcamStatus;
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

    private final WebcamRepository repository = WebcamRepository.getInstance();

    // ── Observers ──────────────────────────────────────────────────────────────

    /** @return LiveData with the current webcam session status. */
    public LiveData<WebcamStatus> getStatus() {
        return repository.getStatus();
    }

    // ── User actions ───────────────────────────────────────────────────────────

    /** Called when the user taps Start — triggers the stream handshake. */
    public void startStream() {
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
}
