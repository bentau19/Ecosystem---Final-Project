package com.example.android.ui.adapters;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.annotation.Nullable;
import androidx.core.content.ContextCompat;
import androidx.recyclerview.widget.RecyclerView;

import com.example.android.R;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

/**
 * RecyclerView adapter for {@link com.example.android.ui.fragments.FolderPickerFragment}.
 *
 * <p>Displays a list of sub-directories for the current navigation level.
 * When the user has navigated below the root, an "↑  .." row is prepended
 * so they can navigate back to the parent directory.
 *
 * <p>Callback convention: {@link OnFolderClickListener#onFolderClicked(File)} is
 * called with {@code null} when the "↑  .." row is tapped (go-up signal).
 */
public class FolderListAdapter extends RecyclerView.Adapter<FolderListAdapter.FolderViewHolder> {

    // ── Callback ──────────────────────────────────────────────────────────────

    public interface OnFolderClickListener {
        /**
         * @param folder The directory that was tapped, or {@code null} to signal
         *               a "navigate up" request (↑ ..) row was tapped).
         */
        void onFolderClicked(@Nullable File folder);
    }

    // ── State ─────────────────────────────────────────────────────────────────

    private final List<File> folders = new ArrayList<>();
    /** Whether to prepend a "↑  .." navigation-up row. */
    private boolean showUpRow = false;
    @Nullable
    private OnFolderClickListener listener;

    // ── Public API ────────────────────────────────────────────────────────────

    public void setListener(@Nullable OnFolderClickListener listener) {
        this.listener = listener;
    }

    /**
     * Replaces the current data set.
     *
     * @param dirs    Sorted list of sub-directories to display.
     * @param showUp  {@code true} to prepend the "↑  .." row (user is not at root).
     */
    public void setData(@NonNull List<File> dirs, boolean showUp) {
        this.folders.clear();
        this.folders.addAll(dirs);
        this.showUpRow = showUp;
        notifyDataSetChanged();
    }

    // ── RecyclerView.Adapter ──────────────────────────────────────────────────

    @NonNull
    @Override
    public FolderViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View v = LayoutInflater.from(parent.getContext())
                .inflate(R.layout.item_folder_row, parent, false);
        return new FolderViewHolder(v);
    }

    @Override
    public void onBindViewHolder(@NonNull FolderViewHolder holder, int position) {
        if (showUpRow && position == 0) {
            // ── "↑  .." row — navigate to parent ─────────────────────────────
            holder.name.setText("↑  ..");
            holder.name.setTextColor(
                    ContextCompat.getColor(holder.itemView.getContext(), R.color.text_muted));
            holder.chevron.setVisibility(View.GONE);
            holder.icon.setVisibility(View.INVISIBLE); // keep spacing, but hide the folder icon
            holder.itemView.setContentDescription(
                    holder.itemView.getContext().getString(R.string.folder_picker_go_up_desc));
            holder.itemView.setOnClickListener(v -> {
                if (listener != null) listener.onFolderClicked(null);
            });
        } else {
            // ── Regular folder row ────────────────────────────────────────────
            int dataIndex = showUpRow ? position - 1 : position;
            File folder = folders.get(dataIndex);
            holder.name.setText(folder.getName());
            holder.name.setTextColor(
                    ContextCompat.getColor(holder.itemView.getContext(), R.color.text_primary));
            holder.chevron.setVisibility(View.VISIBLE);
            holder.icon.setVisibility(View.VISIBLE);
            holder.itemView.setContentDescription(folder.getName());
            holder.itemView.setOnClickListener(v -> {
                if (listener != null) listener.onFolderClicked(folder);
            });
        }
    }

    @Override
    public int getItemCount() {
        return folders.size() + (showUpRow ? 1 : 0);
    }

    // ── ViewHolder ────────────────────────────────────────────────────────────

    static class FolderViewHolder extends RecyclerView.ViewHolder {
        final ImageView icon;
        final TextView name;
        final ImageView chevron;

        FolderViewHolder(@NonNull View itemView) {
            super(itemView);
            icon    = itemView.findViewById(R.id.ivRowIcon);
            name    = itemView.findViewById(R.id.tvFolderName);
            chevron = itemView.findViewById(R.id.ivChevron);
        }
    }
}
