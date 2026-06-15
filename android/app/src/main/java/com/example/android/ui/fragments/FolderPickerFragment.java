package com.example.android.ui.fragments;

import android.content.DialogInterface;
import android.os.Bundle;
import android.os.Environment;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.recyclerview.widget.DividerItemDecoration;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;

import com.example.android.R;
import com.example.android.ui.adapters.FolderListAdapter;
import com.google.android.material.bottomsheet.BottomSheetDialogFragment;

import java.io.File;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.Deque;
import java.util.List;

/**
 * A navigable directory-browser {@link BottomSheetDialogFragment} powered by
 * the {@link File} API.
 *
 * <p>Because it does NOT use Storage Access Framework ({@code ACTION_OPEN_DOCUMENT_TREE}),
 * it has no Android 11+ SAF restriction — the user can select Downloads, DCIM root,
 * storage root, or any other directory the app holds permission to read.
 *
 * <p><b>Required permissions before showing this fragment:</b>
 * <ul>
 *   <li>API 24–29: {@code READ_EXTERNAL_STORAGE}</li>
 *   <li>API 30+: {@code MANAGE_EXTERNAL_STORAGE}
 *       ({@link Environment#isExternalStorageManager()})</li>
 * </ul>
 *
 * <p><b>Usage:</b>
 * <pre>
 *   FolderPickerFragment picker = FolderPickerFragment.newInstance(
 *       Environment.getExternalStorageDirectory());
 *   picker.setCallback(new FolderPickerFragment.FolderSelectedCallback() {
 *       public void onFolderSelected(File folder) { … }
 *       public void onPickerCancelled()           { … }
 *   });
 *   picker.show(getChildFragmentManager(), "folder_picker");
 * </pre>
 *
 * <p><b>Navigation:</b> tap a row to descend into that sub-directory.
 * An "↑  .." row appears at the top whenever the user is below the start directory.
 * The hardware/software back button navigates up one level if possible; otherwise
 * dismisses the sheet and fires {@link FolderSelectedCallback#onPickerCancelled()}.
 *
 * <p><b>Selection:</b> the pinned "Select This Folder" button always selects the
 * directory currently displayed — not a highlighted row — and then dismisses.
 */
public class FolderPickerFragment extends BottomSheetDialogFragment {

    // ── Callback ──────────────────────────────────────────────────────────────

    /**
     * Implemented by the caller (e.g. {@link BackupFragment}) to receive the result.
     */
    public interface FolderSelectedCallback {
        /**
         * The user tapped "Select This Folder".
         *
         * @param folder The directory that was displayed at selection time.
         */
        void onFolderSelected(@NonNull File folder);

        /**
         * The sheet was dismissed without a selection (back press, outside tap,
         * or cancel).
         */
        void onPickerCancelled();
    }

    // ── State ─────────────────────────────────────────────────────────────────

    @Nullable
    private FolderSelectedCallback callback;

    /** Directory currently displayed in the list. */
    @NonNull
    private File currentDir = Environment.getExternalStorageDirectory();

    /**
     * Parent-directory trail — push on descend, pop on go-up.
     * Empty when the user is at the start directory.
     */
    private final Deque<File> backStack = new ArrayDeque<>();

    /**
     * Guards {@link #onDismiss}: true once the user confirms a selection so we
     * don't also fire {@link FolderSelectedCallback#onPickerCancelled()}.
     */
    private boolean selectionConfirmed = false;

    // ── Views ─────────────────────────────────────────────────────────────────

    @Nullable private TextView tvCurrentPath;
    @Nullable private RecyclerView rvFolders;
    @Nullable private TextView tvEmpty;
    @Nullable private FolderListAdapter adapter;

    // ── Factory ───────────────────────────────────────────────────────────────

    /**
     * Creates a new picker starting at {@code startDir}.
     *
     * @param startDir Root of the browsable tree — typically
     *                 {@link Environment#getExternalStorageDirectory()}.
     */
    public static FolderPickerFragment newInstance(@NonNull File startDir) {
        FolderPickerFragment f = new FolderPickerFragment();
        f.currentDir = startDir;
        return f;
    }

    // ── Public API ────────────────────────────────────────────────────────────

    /** Register the callback before calling {@link #show}. */
    public void setCallback(@Nullable FolderSelectedCallback callback) {
        this.callback = callback;
    }

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    @Nullable
    @Override
    public View onCreateView(@NonNull LayoutInflater inflater,
                             @Nullable ViewGroup container,
                             @Nullable Bundle savedInstanceState) {
        return inflater.inflate(R.layout.fragment_folder_picker, container, false);
    }

    @Override
    public void onViewCreated(@NonNull View view, @Nullable Bundle savedInstanceState) {
        super.onViewCreated(view, savedInstanceState);

        tvCurrentPath = view.findViewById(R.id.tvCurrentPath);
        rvFolders     = view.findViewById(R.id.rvFolders);
        tvEmpty       = view.findViewById(R.id.tvEmpty);

        // ── Adapter ───────────────────────────────────────────────────────────
        adapter = new FolderListAdapter();
        adapter.setListener(clickedFolder -> {
            if (clickedFolder == null) {
                navigateUp();
            } else {
                navigateTo(clickedFolder);
            }
        });

        assert rvFolders != null;
        rvFolders.setLayoutManager(new LinearLayoutManager(requireContext()));
        rvFolders.setAdapter(adapter);
        rvFolders.addItemDecoration(
                new DividerItemDecoration(requireContext(), DividerItemDecoration.VERTICAL));

        // ── Select This Folder button ─────────────────────────────────────────
        view.findViewById(R.id.btnSelectFolder).setOnClickListener(v -> confirmSelection());

        // ── Initial load ──────────────────────────────────────────────────────
        loadDirectory(currentDir);
    }

    // ── Dismiss / cancel ──────────────────────────────────────────────────────

    @Override
    public void onDismiss(@NonNull DialogInterface dialog) {
        super.onDismiss(dialog);
        if (!selectionConfirmed && callback != null) {
            callback.onPickerCancelled();
        }
    }

    // ── Navigation ────────────────────────────────────────────────────────────

    /**
     * Descends into {@code dir}, pushing the current directory onto the back stack.
     */
    private void navigateTo(@NonNull File dir) {
        backStack.push(currentDir);
        currentDir = dir;
        loadDirectory(dir);
    }

    /**
     * Returns to the parent directory (pops the back stack).
     * No-op when already at the start directory (back stack is empty).
     */
    private void navigateUp() {
        if (!backStack.isEmpty()) {
            currentDir = backStack.pop();
            loadDirectory(currentDir);
        }
    }

    /**
     * Populates the RecyclerView with the readable sub-directories of {@code dir},
     * updates the breadcrumb, and manages the empty-state view.
     *
     * <p>Hidden directories (names starting with {@code .}) are excluded to match
     * the expected user mental model of "visible" folders.
     */
    private void loadDirectory(@NonNull File dir) {
        // ── Update breadcrumb ─────────────────────────────────────────────────
        if (tvCurrentPath != null) {
            tvCurrentPath.setText(dir.getAbsolutePath());
        }

        // ── Enumerate sub-directories ─────────────────────────────────────────
        List<File> dirs = new ArrayList<>();
        File[] children = dir.listFiles();
        if (children != null) {
            for (File child : children) {
                if (child.isDirectory()
                        && child.canRead()
                        && !child.getName().startsWith(".")) {
                    dirs.add(child);
                }
            }
            // Case-insensitive alphabetical sort
            dirs.sort(Comparator.comparing(f -> f.getName().toLowerCase(java.util.Locale.ROOT)));
        }

        // ── Show "↑ .." row when below start dir ─────────────────────────────
        boolean belowRoot = !backStack.isEmpty();
        if (adapter != null) {
            adapter.setData(dirs, belowRoot);
        }

        // ── Empty state ───────────────────────────────────────────────────────
        // Show empty message only when there are no folder rows AND no "↑ .." row.
        boolean adapterIsEmpty = dirs.isEmpty() && !belowRoot;
        if (tvEmpty != null) {
            tvEmpty.setVisibility(adapterIsEmpty ? View.VISIBLE : View.GONE);
        }
        if (rvFolders != null) {
            rvFolders.setVisibility(adapterIsEmpty ? View.GONE : View.VISIBLE);
        }
    }

    // ── Selection ─────────────────────────────────────────────────────────────

    private void confirmSelection() {
        selectionConfirmed = true;
        if (callback != null) {
            callback.onFolderSelected(currentDir);
        }
        dismiss();
    }
}
