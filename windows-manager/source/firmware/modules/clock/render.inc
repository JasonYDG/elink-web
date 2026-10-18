/* Compile-time clock rendering; scheduling is composed after the display core. */
__attribute__((noinline)) static void clock_face(void){
    char t[40];font(DATE);
    FORMAT(t,"%04u/%02u/%02u",G[2],E[7]+1,E[8]+1);text(12,4,t,0);
    static const char *week[7]={"日","一","二","三","四","五","六"};
    text(96,4,"星期",0);text(124,4,week[G[3]],0);text(146,4,E[9]>=12?"PM":"AM",0);
    line(12,22,238,0);
    font(DIGITS);unsigned h=E[9];if(h>=12)h-=12;if(!h)h=12;
    FORMAT(t,"%02u",h);compressed_ink(DIGITS,11,1,t,0);compressed_ink(DIGITS,111,-12,":",0);
    FORMAT(t,"%02u",E[10]);compressed_ink(DIGITS,139,1,t,0);
    font(MAIN);
    /* The native lunar counters advance without a gateway; keep this useful footer. */
    unsigned lm=G[5]&127,ld=G[6]+1;
    if(lm<12&&ld<=30){char l[24];lunar(l);
        if(S[27]&2)text(2,103,l,0);else {FORMAT(t,"农历%s",l);text(8,103,t,0);}}
    if(S[27]&2)text(100,103,"荷兰",0);
    next_term(t);text(244-width(MAIN,t),103,t,0);
}
