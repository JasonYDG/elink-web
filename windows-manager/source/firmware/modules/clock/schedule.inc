/* Legacy minute entry and view selection; reminder priority is preserved. */
static void photo_calendar(void);
__attribute__((section(".clock.entry"))) void product_clock(unsigned flags){
    if(S[8]||S[7]==1||*(volatile u32 *)0x07fd0564||!time_valid())return;
    dutch_dst();if(product_reminder_tick()||product_album_tick())return;if(S[7]!=0&&S[7]!=3&&S[7]!=6&&S[7]!=8)return;
    u32 date=date_key();
    if(!(flags&128)){
        if(S[7]!=0 && U->valid&&U->date==date&&U->view==S[7])return;
        if(S[7]==0){unsigned interval=S[24];if(!interval||E[10]-DIV(E[10],interval)*interval)return;}
    }
    U->ticks=0;S[25]=0;CALL0(LEDS_OFF);CALL0(0x07fc3f04);
    if(S[7]==6||S[7]==8)photo_calendar();
    else {
        for(unsigned i=0;i<4000;i++){BW[i]=255;RR[i]=0;}
        if(S[7]==3)calendar();else clock_face();
        product_battery(194,4,1);
    }
    U->pending_outside=frame_hash(0);U->pending_red=frame_hash(1);
    U->partial=(S[7]==0&&S[5]!=0&&!(flags&128)&&U->valid&&U->view==0&&U->date==date&&U->hour==E[9]&&
        U->outside==U->pending_outside&&U->red==U->pending_red&&U->count+1<S[6])?S[5]:0;
    if(U->valid==1&&U->view==0&&S[7]!=0)U->valid=3;
    U->pending_date=date;U->pending_hour=E[9];U->pending=1;U->view=S[7];
    CALL0(0x07fc3f68);CALL0(0x07fc40e8);CALL0(0x07fc4174);CALL0(0x07fd1480);
}
__attribute__((section(".reminder.main"),noinline)) int product_view(unsigned view){
    if((view>1&&view!=3)||!time_valid())return 1;
    if(S[8]||(S[7]==1&&view!=3))return 2;
    /* A complete, checked upload can render the photo theme before its first refresh. */
    if(view==3&&((S[7]!=1&&S[7]!=2)||*(volatile u16 *)(S+10)!=8000||
        *(volatile u16 *)(S+14)!=*(volatile u16 *)(S+16)))return 1;
    S[7]=view==3?6:view?3:0;product_clock(128);return 0;
}
