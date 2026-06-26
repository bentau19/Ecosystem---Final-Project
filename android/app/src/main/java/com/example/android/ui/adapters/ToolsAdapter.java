package com.example.android.ui.adapters;

import android.content.res.ColorStateList;
import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.core.content.ContextCompat;
import androidx.recyclerview.widget.RecyclerView;

import com.example.android.R;
import com.example.android.ui.models.ToolItem;

import java.util.List;

/**
 * Adapter for the tool cards in the Actions screen.
 * Each card shows a coloured icon circle, a title, and a subtitle.
 */
public class ToolsAdapter extends RecyclerView.Adapter<ToolsAdapter.ToolViewHolder> {

    private final List<ToolItem> tools;
    private final OnToolClickListener listener;

    public interface OnToolClickListener {
        void onToolClick(ToolItem tool);
    }

    public ToolsAdapter(List<ToolItem> tools, OnToolClickListener listener) {
        this.tools = tools;
        this.listener = listener;
    }

    @NonNull
    @Override
    public ToolViewHolder onCreateViewHolder(@NonNull ViewGroup parent, int viewType) {
        View view = LayoutInflater.from(parent.getContext())
                .inflate(R.layout.item_tool, parent, false);
        return new ToolViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull ToolViewHolder holder, int position) {
        ToolItem tool = tools.get(position);
        boolean enabled = tool.isEnabled();

        holder.toolTitle.setText(tool.getTitle());
        holder.toolSubtitle.setText(tool.getSubtitle());
        holder.toolIcon.setImageResource(tool.getIconRes());

        // Apply accent colour to both the icon and its circle background.
        int accentColor = ContextCompat.getColor(
                holder.itemView.getContext(), tool.getAccentColorRes());
        holder.toolIcon.setImageTintList(ColorStateList.valueOf(accentColor));
        holder.iconBg.setBackgroundResource(tool.getIconBgRes());

        // Dim the whole card while disabled (e.g. clipboard "Sent!" cooldown).
        holder.itemView.setEnabled(enabled);
        holder.itemView.setAlpha(enabled ? 1.0f : 0.45f);

        holder.itemView.setOnClickListener(v -> listener.onToolClick(tool));
    }

    @Override
    public int getItemCount() { return tools.size(); }

    /** Updates the display label of the tool with the given id. */
    public void updateLabel(String toolId, String newLabel) {
        for (int i = 0; i < tools.size(); i++) {
            if (tools.get(i).getId().equals(toolId)) {
                tools.get(i).setTitle(newLabel);
                notifyItemChanged(i);
                return;
            }
        }
    }

    static class ToolViewHolder extends RecyclerView.ViewHolder {
        final TextView  toolTitle;
        final TextView  toolSubtitle;
        final ImageView toolIcon;
        final View      iconBg;

        ToolViewHolder(View itemView) {
            super(itemView);
            toolTitle    = itemView.findViewById(R.id.toolTitle);
            toolSubtitle = itemView.findViewById(R.id.toolSubtitle);
            toolIcon     = itemView.findViewById(R.id.toolIcon);
            iconBg       = itemView.findViewById(R.id.iconBg);
        }
    }
}
