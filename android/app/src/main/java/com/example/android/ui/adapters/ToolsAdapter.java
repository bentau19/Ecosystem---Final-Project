package com.example.android.ui.adapters;

import android.view.LayoutInflater;
import android.view.View;
import android.view.ViewGroup;
import android.widget.ImageView;
import android.widget.TextView;

import androidx.annotation.NonNull;
import androidx.recyclerview.widget.RecyclerView;

import com.example.android.R;
import com.example.android.ui.models.ToolItem;

import java.util.List;

public class ToolsAdapter extends RecyclerView.Adapter<ToolsAdapter.ToolViewHolder> {
    private List<ToolItem> tools;
    private OnToolClickListener listener;

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
        View view = LayoutInflater.from(parent.getContext()).inflate(R.layout.item_tool, parent, false);
        return new ToolViewHolder(view);
    }

    @Override
    public void onBindViewHolder(@NonNull ToolViewHolder holder, int position) {
        ToolItem tool = tools.get(position);
        holder.title.setText(tool.getTitle());
        holder.icon.setImageResource(tool.getIconRes());
        holder.itemView.setOnClickListener(v -> listener.onToolClick(tool));
    }

    @Override
    public int getItemCount() { return tools.size(); }

    static class ToolViewHolder extends RecyclerView.ViewHolder {
        TextView title;
        ImageView icon;

        ToolViewHolder(View itemView) {
            super(itemView);
            title = itemView.findViewById(R.id.toolTitle);
            icon = itemView.findViewById(R.id.toolIcon);
        }
    }
}
