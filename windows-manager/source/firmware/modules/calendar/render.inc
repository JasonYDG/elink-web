/* Compile-time calendar module; uses the shared native rendering primitives. */
/* Invert existing black type into a solid black/red band with white lettering. */
static void band(int x,int y,int w,int h,int red){
    for(int j=y;j<y+h;j++)for(int i=x;i<x+w;i++){
        unsigned pos=(249-i)*16+(j>>3),mask=128>>(j&7);
        if(!(BW[pos]&mask)){BW[pos]|=mask;RR[pos]&=~mask;}else pixel(i,j,red);
    }
}
__attribute__((noinline)) static void calendar(void){
    char t[40];font(MAIN);FORMAT(t,"%u月",E[7]+1);text(5,1,t,0);
    font(SMALL);
    unsigned ordinal=E[8]+1;for(unsigned m=0;m<E[7];m++)ordinal+=month_days(G[2],m);
    unsigned wd=G[3]?G[3]:7,weekno=DIV(ordinal+10-wd,7),jan=(wd+7-((ordinal-1)-DIV(ordinal-1,7)*7));if(jan>7)jan-=7;
    if(!weekno){unsigned prev=G[2]-1,j=jan+7-(1+!(prev&3));if(j>7)j-=7;weekno=(j==4||(j==3&&!(prev&3)))?53:52;}
    else if(weekno==53&&jan!=4&&(jan!=3||(G[2]&3)))weekno=1;
    FORMAT(t,"第%u周",weekno);text(52,5,t,0);
    static const char *week[7]={"日","一","二","三","四","五","六"};font(MAIN);
    for(unsigned i=0;i<7;i++){
        text(8+i*22,23,week[i],0);band(6+i*22,23,22,19,i==0||i==6);
    }
    unsigned first=(G[3]+7-(E[8]-DIV(E[8],7)*7));if(first>=7)first-=7;
    unsigned days=month_days(G[2],E[7]),dense=first+days>35,pitch=dense?13:15;
    u32 digits=dense?SMALL:DAYS;font(digits);
    unsigned col=first,row=0;
    for(unsigned day=1;day<=days;day++){
        int x=6+col*22,y=44+row*pitch;
        FORMAT(t,"%u",day);text(x+((22-width(digits,t))>>1),y,t,0);
        if(day==E[8]+1){
            /* Existing digit ink becomes white, cell whitespace becomes red. */
            band(x+1,y,20,pitch,1);
        }
        if(++col==7){col=0;row++;}
    }
    line(6,21,238,0);for(int y=23;y<122;y++)pixel(167,y,0);
    FORMAT(t,"%u",G[2]);product_ink(MAIN,171,24,t,1);
    static const char *stem[10]={"甲","乙","丙","丁","戊","己","庚","辛","壬","癸"};
    static const char *branch[12]={"子","丑","寅","卯","辰","巳","午","未","申","酉","戌","亥"};
    static const char *animal[12]={"鼠","牛","虎","兔","龙","蛇","马","羊","猴","鸡","狗","猪"};
    unsigned a=G[2]-4,b=a-DIV(a,12)*12;FORMAT(t,"%s%s%s年",stem[a-DIV(a,10)*10],branch[b],animal[b]);
    font(MAIN);text(171,43,t,0);line(171,62,73,0);
    /* A leap month needs five 18px cells; only that rare row drops to 12px. */
    lunar(t);if(G[5]&128){font(SMALL);text(171,68,t,0);font(MAIN);}else text(171,64,t,0);line(171,83,73,0);
    next_term(t);char ch=t[6];t[6]=0;text(171,85,t,0);t[6]=ch;text(171,103,t+6,0);
}
