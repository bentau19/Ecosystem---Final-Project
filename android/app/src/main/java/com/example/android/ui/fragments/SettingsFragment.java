package com.example.android.ui.fragments;

import android.os.Bundle;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageButton;

import androidx.annotation.NonNull;
import androidx.appcompat.widget.SwitchCompat;
import androidx.fragment.app.Fragment;
import androidx.lifecycle.ViewModelProvider;

import com.example.android.R;
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

    /**
     * Guards switch listeners while the LiveData observer applies a value programmatically.
     * Without this, a PC-pushed state change would cause:
     *   observer → setChecked() → listener → viewModel.setX() → ACTION_PUSH_SETTINGS
     * which pushes the same value right back to the PC (loop).
     */
    private boolean programmaticUpdate = false;

    private SettingsViewModel settingsViewModel;

    private SwitchCompat switchDarkMode;
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
        switchDarkMode         = view.findViewById(R.id.switchDarkMode);
        switchAutoLaunch       = view.findViewById(R.id.switchAutoLaunch);
        switchBackup           = view.findViewById(R.id.switchBackup);
        switchVirtualDrive     = view.findViewById(R.id.switchVirtualDrive);
        switchClipboardSync    = view.findViewById(R.id.switchClipboardSync);
        switchWebcam           = view.findViewById(R.id.switchWebcam);

        // 3. Set initial switch states BEFORE attaching listeners so the first
        //    setChecked() does not trigger a repository write or a PC push.
        switchDarkMode.setChecked(settingsViewModel.isDarkMode());
        switchAutoLaunch.setChecked(settingsViewModel.isAutoLaunch());
        switchBackup.setChecked(settingsViewModel.isBackupEnabled());
        switchVirtualDrive.setChecked(settingsViewModel.isVirtualDriveEnabled());
        switchClipboardSync.setChecked(settingsViewModel.isClipboardEnabled());
        switchWebcam.setChecked(settingsViewModel.isWebcamEnabled());

        // 4. Observe LiveData for all tool settings.
        //    Dark mode synced bidirectionally: observer fires when PC pushes a change.
        settingsViewModel.getDarkMode().observe(getViewLifecycleOwner(), enabled -> {
            if (switchDarkMode.isChecked() != enabled) {
                programmaticUpdate = true;
                switchDarkMode.setChecked(enabled);
                programmaticUpdate = false;
                // Theme application is handled by the MainActivity observer so it works
                // regardless of which fragment is visible (including when PC pushes).
            }
        });

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
        switchDarkMode.setOnCheckedChangeListener((btn, checked) -> {
            if (!programmaticUpdate) {
                // setDarkMode() persists + postValue → MainActivity observer applies theme.
                settingsViewModel.setDarkMode(checked);
            }
        });

        switchAutoLaunch.setOnCheckedChangeListener((btn, checked) ->
                settingsViewModel.setAutoLaunch(checked));

        switchBackup.setOnCheckedChangeListener((btn, checked) -> {
            if (!programmaticUpdate) {
                settingsViewModel.setBackupEnabled(checked);
            }
        });

        switchVirtualDrive.setOnCheckedChangeListener((btn, checked) -> {
            if (!programmaticUpdate) {
                settingsViewModel.setVirtualDriveEnabled(checked);
            }
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
}
