package com.musab.newalcloud;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.os.Bundle;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.recyclerview.widget.LinearLayoutManager;
import androidx.recyclerview.widget.RecyclerView;
import com.google.android.material.button.MaterialButton;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends AppCompatActivity {
    private static final String SYSTEM_PROMPT = "You are NewAI, an expert assistant and coding assistant. Answer in the user language. Use Markdown when useful. Put source code inside fenced code blocks with the language name.";
    private static final int MAX_TOKENS = 4096;
    private static final double TEMPERATURE = 0.2;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final android.os.Handler ui = new android.os.Handler(android.os.Looper.getMainLooper());
    private final List<RemoteChat.Msg> history = new ArrayList<>();
    private final StringBuilder live = new StringBuilder();
    private final Object renderLock = new Object();
    private boolean renderScheduled, busy;
    private ChatHistoryStore historyStore;
    private ChatAdapter adapter;
    private RecyclerView chatList;
    private EditText inputBox;
    private TextView status;
    private View rootView, headerView, inputBar, emptyView;
    private MaterialButton sendButton, clearButton, newChatButton, freeButton;
    private volatile RemoteChat client;

    @Override protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        historyStore = new ChatHistoryStore(this);
        rootView=findViewById(R.id.rootView); headerView=findViewById(R.id.headerView); inputBar=findViewById(R.id.inputBar);
        status=findViewById(R.id.status); chatList=findViewById(R.id.chatList); inputBox=findViewById(R.id.inputBox);
        sendButton=findViewById(R.id.sendButton); clearButton=findViewById(R.id.clearButton);
        newChatButton=findViewById(R.id.agentButton); freeButton=findViewById(R.id.loadModelButton); emptyView=findViewById(R.id.emptyView);
        adapter=new ChatAdapter();
        adapter.setActions(new ChatAdapter.Actions(){
            public void onRerun(){} public void onFiles(){} public void onOpenTermux(){} public void onUndo(){}
            public void onCopy(String text){copyText(text);}
        });
        chatList.setLayoutManager(new LinearLayoutManager(this)); chatList.setAdapter(adapter);
        newChatButton.setText("🆕 جديد"); freeButton.setText("☁ مجاني"); freeButton.setEnabled(false);
        status.setText("جاهز • FreeLLMAPI Auto Free • بدون API key");
        loadHistory(); setupExamples(); installInsets();
        newChatButton.setOnClickListener(v->clearChat()); clearButton.setOnClickListener(v->clearChat()); sendButton.setOnClickListener(v->sendOrStop());
        inputBox.addTextChangedListener(new android.text.TextWatcher(){
            public void beforeTextChanged(CharSequence s,int st,int c,int a){}
            public void onTextChanged(CharSequence s,int st,int b,int c){if(!busy)sendButton.setEnabled(s.toString().trim().length()>0);}
            public void afterTextChanged(android.text.Editable e){}
        });
    }

    private void installInsets(){
        WindowCompat.setDecorFitsSystemWindows(getWindow(),false); final int top=headerView.getPaddingTop();
        ViewCompat.setOnApplyWindowInsetsListener(rootView,(v,insets)->{
            Insets bars=insets.getInsets(WindowInsetsCompat.Type.systemBars()); Insets ime=insets.getInsets(WindowInsetsCompat.Type.ime());
            headerView.setPadding(headerView.getPaddingLeft(),top+bars.top,headerView.getPaddingRight(),headerView.getPaddingBottom());
            LinearLayout.LayoutParams lp=(LinearLayout.LayoutParams)inputBar.getLayoutParams(); lp.bottomMargin=Math.max(bars.bottom,ime.bottom); inputBar.setLayoutParams(lp);
            if(ime.bottom>0)inputBar.post(this::scrollToEnd); return insets;});
        ViewCompat.requestApplyInsets(rootView);
    }

    private void setupExamples(){
        LinearLayout box=findViewById(R.id.examples);
        String[] examples={"💻 اكتب لي كود Python لقراءة ملف CSV","🧠 اشرح لي P vs NP بطريقة بسيطة","🛠 ساعدني أبني مشروع Android"};
        for(String text:examples){
            TextView item=new TextView(this); item.setText(text); item.setTextColor(0xFFE6EDF3); item.setTextSize(15); item.setPadding(dp(18),dp(16),dp(18),dp(16)); item.setBackgroundResource(R.drawable.bubble_assistant);
            LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(-1,-2); lp.setMargins(0,0,0,dp(10)); box.addView(item,lp);
            item.setOnClickListener(v->{inputBox.setText(text.substring(text.indexOf(" ")+1));inputBox.setSelection(inputBox.length());sendButton.setEnabled(true);});
        }
        updateEmptyState();
    }

    private void loadHistory(){
        List<ChatMessage> saved=historyStore.loadAll();
        for(ChatMessage m:saved){if(m.role==ChatMessage.ROLE_USER)history.add(new RemoteChat.Msg("user",m.text));else if(m.role==ChatMessage.ROLE_ASSISTANT)history.add(new RemoteChat.Msg("assistant",m.text));}
        adapter.setAll(buildDisplayMessages(saved)); updateEmptyState(); scrollToEnd();
    }

    private List<ChatMessage> buildDisplayMessages(List<ChatMessage> source){
        List<ChatMessage> out=new ArrayList<>(); for(ChatMessage m:source){if(m.role!=ChatMessage.ROLE_ASSISTANT)out.add(m);else splitAssistant(out,m);} return out;
    }

    private void splitAssistant(List<ChatMessage> out,ChatMessage m){
        String s=m.text==null?"":m.text; String fence="\u0060\u0060\u0060"; int pos=0;
        while(pos<s.length()){
            int start=s.indexOf(fence,pos); if(start<0){String t=s.substring(pos).trim();if(!t.isEmpty())out.add(new ChatMessage(m.id,ChatMessage.ROLE_ASSISTANT,t,m.timeMs));break;}
            String before=s.substring(pos,start).trim(); if(!before.isEmpty())out.add(new ChatMessage(m.id,ChatMessage.ROLE_ASSISTANT,before,m.timeMs));
            int lineEnd=s.indexOf("\n",start); int close=lineEnd<0?-1:s.indexOf(fence,lineEnd+1);
            if(close<0){String code=s.substring(start+3).trim();if(!code.isEmpty())out.add(new ChatMessage(m.id,ChatMessage.ROLE_CODE,code,m.timeMs));break;}
            String code=s.substring(lineEnd+1,close).trim(); if(!code.isEmpty())out.add(new ChatMessage(m.id,ChatMessage.ROLE_CODE,code,m.timeMs)); pos=close+3;
        }
    }

    private void sendOrStop(){
        if(busy){RemoteChat c=client;if(c!=null)c.cancel();return;}
        String q=inputBox.getText().toString().trim();if(q.isEmpty())return; inputBox.setText("");
        history.add(new RemoteChat.Msg("user",q)); long id=historyStore.append(ChatMessage.ROLE_USER,q); adapter.add(new ChatMessage(id,ChatMessage.ROLE_USER,q,System.currentTimeMillis()));
        synchronized(live){live.setLength(0);} setBusy(true); status.setText("جاري التوجيه تلقائياً إلى نموذج مجاني…"); updateEmptyState(); scrollToEnd();
        List<RemoteChat.Msg> turns=new ArrayList<>(); turns.add(new RemoteChat.Msg("system",SYSTEM_PROMPT)); turns.addAll(history);
        RemoteChat c=new RemoteChat();client=c;
        executor.execute(()->{try{RemoteChat.Result r=c.chat(Providers.ENDPOINT,"",Providers.MODEL,turns,MAX_TOKENS,TEMPERATURE,delta->{synchronized(live){live.append(delta);}scheduleRender();});
            String metrics=String.format(Locale.US,"☁ %s • أول token %dms • إجمالي %dms",Providers.MODEL,r.firstTokenMs,r.totalMs);ui.post(()->finishTurn(r.text,null,metrics));
        }catch(RemoteChat.ApiException e){ui.post(()->finishTurn("",describe(e),"فشل الطلب"));}catch(Exception e){String m=e.getMessage()==null?e.getClass().getSimpleName():e.getMessage();ui.post(()->finishTurn("",m,"فشل الاتصال"));}});
    }

    private void finishTurn(String answer,String error,String metrics){
        synchronized(live){live.setLength(0);}
        if(answer!=null&&!answer.trim().isEmpty()){history.add(new RemoteChat.Msg("assistant",answer));historyStore.append(ChatMessage.ROLE_ASSISTANT,answer);}
        else if(!history.isEmpty()&&"user".equals(history.get(history.size()-1).role))history.remove(history.size()-1);
        status.setText(error!=null?error:metrics); setBusy(false); adapter.setAll(buildDisplayMessages(historyStore.loadAll())); updateEmptyState(); scrollToEnd();
    }

    private static String describe(RemoteChat.ApiException e){
        StringBuilder b=new StringBuilder("HTTP ").append(e.code); if(e.code==429)b.append(" — حد الاستخدام المجاني"); else if(e.code==401||e.code==403)b.append(" — رفض الوصول إلى المسار المجاني"); else if(e.code==404)b.append(" — المسار أو النموذج غير متاح");
        String body=e.body==null?"":e.body.trim(); if(!body.isEmpty())b.append("\n").append(body.length()>300?body.substring(0,300)+"…":body); return b.toString();
    }

    private void scheduleRender(){
        synchronized(renderLock){if(renderScheduled)return;renderScheduled=true;}
        ui.postDelayed(()->{synchronized(renderLock){renderScheduled=false;} String text; synchronized(live){text=live.toString();}
            if(adapter.getCount()>0)adapter.updateLast(new ChatMessage(-1,ChatMessage.ROLE_ASSISTANT,text,System.currentTimeMillis())); else adapter.add(new ChatMessage(-1,ChatMessage.ROLE_ASSISTANT,text,System.currentTimeMillis())); scrollToEnd();},50);
    }

    private void setBusy(boolean b){busy=b;sendButton.setText(b?"⏹":"➤");sendButton.setEnabled(b||inputBox.getText().toString().trim().length()>0);newChatButton.setEnabled(!b);clearButton.setEnabled(!b);}
    private void clearChat(){if(busy)return;history.clear();historyStore.clear();adapter.setAll(new ArrayList<>());status.setText("محادثة جديدة • FreeLLMAPI Auto Free");updateEmptyState();}
    private void updateEmptyState(){emptyView.setVisibility(adapter.getCount()==0&&!busy?View.VISIBLE:View.GONE);}
    private void copyText(String text){ClipboardManager cm=(ClipboardManager)getSystemService(CLIPBOARD_SERVICE);if(cm!=null)cm.setPrimaryClip(ClipData.newPlainText("NewAI",text));status.setText("تم النسخ ✓");}
    private void scrollToEnd(){if(adapter.getCount()>0)chatList.scrollToPosition(adapter.getCount()-1);}
    private int dp(int v){return Math.round(v*getResources().getDisplayMetrics().density);}
    @Override protected void onDestroy(){RemoteChat c=client;if(c!=null)c.cancel();executor.shutdownNow();historyStore.close();super.onDestroy();}
}