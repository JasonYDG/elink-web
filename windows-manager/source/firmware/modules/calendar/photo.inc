/* Shared date overlay for direct uploads and frames loaded by the image album module. */
__attribute__((section(".clock.rodata"))) static const char photo_year_month[]="%u/%02u";
__attribute__((section(".clock.rodata"))) static const char photo_weekdays[]="日一二三四五六";
__attribute__((section(".reminder.extra"),noinline)) static void photo_label(int y,const char *s){
    font(SMALL);text(212-width(SMALL,s)/2,y,s,0);
}
__attribute__((section(".clock.extra"),noinline)) static void photo_day(unsigned day){
    unsigned tens=DIV(day,10);char t[3]={'0'+tens,'0'+day-tens*10,0};
    compressed_ink(PHOTO_DAYS,185,15,t,1);
}
__attribute__((section(".reminder.main"),noinline)) static void photo_calendar(void){
    char t[40];
    for(unsigned i=0;i<(250-174)*16;i++){BW[i]=255;RR[i]=0;}
    FORMAT(t,photo_year_month,G[2],E[7]+1);photo_label(2,t);
    photo_day(E[8]+1);
    font(MAIN);text(185,62,"星期",0);
    unsigned w=G[3]*3;for(unsigned i=0;i<3;i++)t[i]=photo_weekdays[w+i];t[3]=0;text(221,62,t,0);
    lunar(t);photo_label(84,t);
    next_term(t);int x=212-(36+width(SMALL,t+6))/2;char ch=t[6];t[6]=0;
    font(MAIN);text(x,101,t,0);t[6]=ch;font(SMALL);text(x+36,106,t+6,0);
}
