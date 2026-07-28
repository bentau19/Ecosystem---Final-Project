package com.example.android.ui.fragments;

<<<<<<< HEAD
import android.app.AlertDialog;
import android.content.Intent;
import android.os.Bundle;
import android.util.Log;
=======
import android.os.Bundle;
>>>>>>> main
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageButton;

import androidx.annotation.NonNull;
<<<<<<< HEAD
import androidx.annotation.Nullable;
=======
>>>>>>> main
import androidx.appcompat.widget.SwitchCompat;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;

import com.example.android.R;
<<<<<<< HEAD
import com.example.android.utils.StoragePermissions;
=======
>>>>>>> main
import com.example.android.viewmodel.SettingsViewModel;

/**
 * Settings screen — four toggles (Auto-launch, Virtual Drive, Clipboard Sync, Camera Mirror).
 * Settings are persisted immediately on each switch change.
 *
 * <h3>Switch lifecycle</h3>
 * <ol>
 *   <li>Initial state is read synchronously from {@link SettingsViewModel} and set on
 *       the switches <em>before</em> the {@code OnCheckedChangeListener} is attached,
 *       so the initial {@code setChecked()} call never triggers a repository write.</li>
 *   <li>The {@code programmaticUpdate} flag guards against the LiveData observer
 *       → {@code setChecked()} → listener → ViewModel loop that would occur when the
 *       connected PC pushes a state change via
 *       {@link com.example.android.network.handlers.SettingsChannelHandler}.</li>
 * </ol>
 *
 * <h3>View access</h3>
 * Uses {@code view.findViewById()} — ViewBinding is not enabled in this project.
 */
public class SettingsFragment extends Fragment {

<<<<<<< HEAD
    private static final String TAG = "SettingsFragment";

    /** Return code from the system All-files-access screen (Virtual Drive gate). */
    private static final int REQ_ALL_FILES_ACCESS = 3001;

=======
>>>>>>> main
    /**
     * Guards switch listeners while the LiveData observer applies a value programmatically.
     * Without this, a PC-pushed state change would cause:
     *   observer → setChecked() → listener → viewModel.setX() → ACTION_PUSH_SETTINGS
     * which pushes the same value right back to the PC (loop).
     */
    private boolean programmaticUpdate = false;

    private SettingsViewModel settingsViewModel;

    private SwitchCompat switchAutoLaunch;
    private SwitchCompat switchBackup;
    private SwitchCompat switchVirtualDrive;
    private SwitchCompat switchClipboardSync;
    private SwitchCompat switchWebcam;

    @Override
    public View onCreateView(@NonNull LayoutInflater inflater,
                             ViewGroup container,
                             Bundle savedInstanceState) {
        return inflater.inflate(R.layout.fragment_settings, container, false);
    }

    @Override
    public void onViewCreated(@NonNull View view, Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);

        // 1. ViewModel — uses built-in AndroidViewModelFactory (no custom factory needed)
        settingsViewModel = new ViewModelProvider(this).get(SettingsViewModel.class);

        // 2. View references
        ImageButton btnBack    = view.findViewById(R.id.btnBack);
        switchAutoLaunch       = view.findViewById(R.id.switchAutoLaunch);
        switchBackup           = view.findViewById(R.id.switchBackup);
        switchVirtualDrive     = view.findViewById(R.id.switchVirtualDrive);
        switchClipboardSync    = view.findViewById(R.id.switchClipboardSync);
        switchWebcam           = view.findViewById(R.id.switchWebcam);

        // 3. Set initial switch states BEFORE attaching listeners so the first
        //    setChecked() does not trigger a repository write or a PC push.
        switchAutoLaunch.setChecked(settingsViewModel.isAutoLaunch());
        switchBackup.setChecked(settingsViewModel.isBackupEnabled());
        switchVirtualDrive.setChecked(settingsViewModel.isVirtualDriveEnabled());
        switchClipboardSync.setChecked(settingsViewModel.isClipboardEnabled());
        switchWebcam.setChecked(settingsViewModel.isWebcamEnabled());

        // 4. Observe LiveData for all tool settings.
        //    Backup is phone-local (no PC push) but observed for consistency — if
        //    the setting ever changes programmatically the switch stays in sync.
        settingsViewModel.getBackupEnabled().observe(getViewLifecycleOwner(), enabled -> {
            if (switchBackup.isChecked() != enabled) {
                programmaticUpdate = true;
                switchBackup.setChecked(enabled);
                programmaticUpdate = false;
            }
        });

        // PC-synced settings (Virtual Drive, Clipboard, Webcam): observer fires when the
        // connected PC pushes a state change via SettingsChannelHandler → SettingsRepository
        // → LiveData. programmaticUpdate suppresses the listener so we don't echo back.

        settingsViewModel.getVirtualDriveEnabled().observe(getViewLifecycleOwner(), enabled -> {
            if (switchVirtualDrive.isChecked() != enabled) {
                programmaticUpdate = true;
                switchVirtualDrive.setChecked(enabled);
                programmaticUpdate = false;
            }
        });

        settingsViewModel.getClipboardEnabled().observe(getViewLifecycleOwner(), enabled -> {
            if (switchClipboardSync.isChecked() != enabled) {
                programmaticUpdate = true;
                switchClipboardSync.setChecked(enabled);
                programmaticUpdate = false;
            }
        });

        settingsViewModel.getWebcamEnabled().observe(getViewLifecycleOwner(), enabled -> {
            if (switchWebcam.isChecked() != enabled) {
                programmaticUpdate = true;
                switchWebcam.setChecked(enabled);
                programmaticUpdate = false;
            }
        });

        // Auto-launch has no remote sync, so no LiveData observation needed — the
        // initial value set in step 3 is sufficient.

        // 5. Attach listeners AFTER initial state is set
        switchAutoLaunch.setOnCheckedChangeListener((btn, checked) ->
                settingsViewModel.setAutoLaunch(checked));

        switchBackup.setOnCheckedChangeListener((btn, checked) -> {
            if (!programmaticUpdate) {
                settingsViewModel.setBackupEnabled(checked);
            }
        });

        switchVirtualDrive.setOnCheckedChangeListener((btn, checked) -> {
<<<<<<< HEAD
            if (programmaticUpdate) return;
            if (checked && !StoragePermissions.hasAllFilesAccess()) {
                promptForAllFilesAccess();
                return;
            }
            settingsViewModel.setVirtualDriveEnabled(checked);
=======
            if (!programmaticUpdate) {
                settingsViewModel.setVirtualDriveEnabled(checked);
            }
>>>>>>> main
        });

        switchClipboardSync.setOnCheckedChangeListener((btn, checked) -> {
            if (!programmaticUpdate) {
                settingsViewModel.setClipboardEnabled(checked);
            }
        });

        switchWebcam.setOnCheckedChangeListener((btn, checked) -> {
            if (!programmaticUpdate) {
                settingsViewModel.setWebcamEnabled(checked);
            }
        });

        // 6. Back navigation — same pattern as BackupFragment / FolderPickerFragment
        btnBack.setOnClickListener(v -> requireActivity().onBackPressed());
    }
<<<<<<< HEAD

    // ── Virtual Drive storage permission ──────────────────────────────────────

    /**
     * Asks for All files access before the Virtual Drive may be enabled.
     *
     * <p>The drive maps the phone's storage to a Windows drive letter through the
     * raw File API. Without this permission the mount still succeeds and browsing
     * works — only writes fail, with the PC reporting a permission error for every
     * copy. Enabling the tool in that state produces a drive that looks healthy and
     * silently refuses work, so unlike Backup (which degrades gracefully and offers
     * "Skip") there is no proceed-anyway option here: declining leaves the switch
     * off.
     */
    private void promptForAllFilesAccess() {
        new AlertDialog.Builder(requireContext())
                .setTitle(R.string.vdrive_storage_permission_title)
                .setMessage(R.string.vdrive_storage_permission_message)
                .setPositiveButton(R.string.vdrive_storage_permission_grant,
                        (d, w) -> StoragePermissions.openSettings(this, REQ_ALL_FILES_ACCESS))
                .setNegativeButton(android.R.string.cancel, (d, w) -> revertVirtualDriveSwitch())
                .setOnCancelListener(d -> revertVirtualDriveSwitch())
                .show();
    }

    /** Puts the switch back to off without echoing the change to the ViewModel or PC. */
    private void revertVirtualDriveSwitch() {
        programmaticUpdate = true;
        switchVirtualDrive.setChecked(false);
        programmaticUpdate = false;
    }

    @Override
    public void onActivityResult(int requestCode, int resultCode, @Nullable Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQ_ALL_FILES_ACCESS) return;

        // The settings screen returns no meaningful resultCode — read the actual state.
        if (StoragePermissions.hasAllFilesAccess()) {
            Log.d(TAG, "All Files Access granted — enabling Virtual Drive");
            settingsViewModel.setVirtualDriveEnabled(true);
        } else {
            Log.d(TAG, "All Files Access not granted — Virtual Drive stays off");
            revertVirtualDriveSwitch();
        }
    }
=======
>>>>>>> main
}
